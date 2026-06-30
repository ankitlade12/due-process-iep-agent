"""Ingest the messy inputs parents actually have.

Real families do not arrive with structured ``ServiceLog`` objects — they have a
spreadsheet the school exported, a PDF of session notes, or a photo of a printed
log. This module turns those into the structured logs the deterministic core
needs:

  * :func:`load_logs_csv` — service logs from CSV/TSV, with fuzzy header mapping
    and status inference (no dependency).
  * :func:`extract_text_from_pdf` — text from a born-digital PDF (needs ``pypdf``).
  * :func:`read_iep_image` — a scanned IEP page transcribed by Qwen's vision
    model, then fed to the normal extractor.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from .llm.client import LLMClient
from .models import ExcusedClass, LogStatus, ServiceLog, SourceKind, SourceRef
from .privacy import Redactor

# Lower-cased header text -> canonical field. Covers the variants schools use.
_HEADER_ALIASES = {
    "date": "date", "session date": "date", "service date": "date", "day": "date",
    "minutes": "minutes", "mins": "minutes", "min": "minutes",
    "duration": "minutes", "minutes delivered": "minutes",
    "delivered minutes": "minutes",
    "status": "status", "attendance": "status", "outcome": "status",
    "reason": "reason", "notes": "reason", "missed reason": "reason",
    "comment": "reason", "comments": "reason",
    "provider": "provider", "therapist": "provider", "clinician": "provider",
    "staff": "provider", "service provider": "provider",
    "setting": "setting", "group size": "group_size",
}

_MISSED_WORDS = {"missed", "absent", "no", "n", "cancelled", "canceled",
                 "not held", "no show", "0"}
_DELIVERED_WORDS = {"delivered", "present", "yes", "y", "held", "completed",
                    "attended", "provided"}


def _canonical_headers(fieldnames: List[str]) -> dict:
    mapping = {}
    for name in fieldnames or []:
        key = (name or "").strip().lower()
        if key in _HEADER_ALIASES:
            mapping[name] = _HEADER_ALIASES[key]
    return mapping


def _parse_date(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(raw: str) -> int:
    m = re.search(r"\d+", raw or "")
    return int(m.group()) if m else 0


def _infer_status(status_raw: str, minutes: int,
                  scheduled_minutes: Optional[int]) -> LogStatus:
    s = (status_raw or "").strip().lower()
    if s in _MISSED_WORDS:
        return LogStatus.MISSED
    if s in _DELIVERED_WORDS or s == "short":
        if s == "short":
            return LogStatus.SHORT
        return LogStatus.DELIVERED
    # No usable status text — infer from minutes.
    if minutes <= 0:
        return LogStatus.MISSED
    if scheduled_minutes and minutes < scheduled_minutes:
        return LogStatus.SHORT
    return LogStatus.DELIVERED


def load_logs_csv(
    source: str,
    commitment_id: str,
    *,
    scheduled_minutes: Optional[int] = None,
    delimiter: Optional[str] = None,
    source_uri: str = "",
) -> List[ServiceLog]:
    """Parse service logs from CSV/TSV text or a file path.

    Args:
        source: CSV text, or a path to a .csv/.tsv file.
        commitment_id: the commitment these logs belong to.
        scheduled_minutes: the per-session minutes the IEP requires (lets a row
            with fewer delivered minutes be inferred as SHORT).
        delimiter: override the delimiter (auto-detected from .tsv otherwise).
    """
    text = source
    if "\n" not in source and Path(source).exists():
        text = Path(source).read_text(encoding="utf-8")
        if delimiter is None and source.lower().endswith(".tsv"):
            delimiter = "\t"

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter or ",")
    headers = _canonical_headers(reader.fieldnames or [])
    if "date" not in headers.values():
        raise ValueError(
            "Could not find a date column. Expected a header like "
            f"'date' / 'session date'. Saw: {reader.fieldnames}"
        )

    logs: List[ServiceLog] = []
    for i, row in enumerate(reader):
        fields = {}
        for original, canonical in headers.items():
            fields[canonical] = (row.get(original) or "").strip()

        d = _parse_date(fields.get("date", ""))
        if d is None:
            continue  # skip rows without a parseable date
        minutes = _parse_int(fields.get("minutes", ""))
        status = _infer_status(fields.get("status", ""), minutes, scheduled_minutes)
        if status == LogStatus.MISSED:
            minutes = 0

        logs.append(ServiceLog(
            id=f"{commitment_id}-row{i:03d}",
            commitment_id=commitment_id,
            date=d,
            minutes_delivered=minutes,
            status=status,
            provider=fields.get("provider", ""),
            missed_reason_text=fields.get("reason", ""),
            excused=ExcusedClass.UNCLASSIFIED,
            source_ref=SourceRef(
                kind=SourceKind.SERVICE_LOG,
                locator=f"row {i + 1}",
                description=f"Imported log row {i + 1} ({d.isoformat()})",
                uri=source_uri,
                record_id=f"{commitment_id}-row{i:03d}",
            ),
        ))
    return logs


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a born-digital PDF (requires ``pypdf``)."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError(
            "Reading PDFs needs pypdf. Install with pip install 'due-process[ingest]'."
        ) from exc
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_VISION_PROMPT = (
    "This is a page from a student's IEP. Transcribe the special-education and "
    "related-services section: list each service with its frequency, duration "
    "(minutes), setting (individual/group), and location (pull-out/push-in). "
    "Output only the transcribed service lines, one per line."
)


def read_iep_image(
    image_path: str,
    client: LLMClient,
    *,
    prompt: str = _VISION_PROMPT,
    redactor: Optional[Redactor] = None,
) -> str:
    """Transcribe a scanned/photographed IEP page via Qwen's vision model.

    Returns the services text, ready to pass to
    :func:`due_process.llm.extraction.extract_commitments`. When a ``redactor`` is
    supplied, the *returned transcription* is scrubbed of known PII so it is safe
    to store or display. (The image itself is still sent to the cloud, which on a
    real IEP contains PII — redact the image or use the self-hosted model for
    fully private vision.)
    """
    import base64

    data = Path(image_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = "image/png" if image_path.lower().endswith("png") else "image/jpeg"
    text = client.complete_vision(prompt, b64, mime=mime).text
    if redactor is not None:
        text, _ = redactor.redact(text)
    return text
