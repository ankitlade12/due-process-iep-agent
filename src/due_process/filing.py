"""State filing guidance + an evidence packet you can actually file.

A federal-floor letter isn't filable on its own — a real state complaint goes to
a *specific* state education agency, and you attach the *exhibits* that prove it.
This module provides:

  * :func:`filing_instructions` — where and how to file, per state (the federal
    floor for states not yet localized), and
  * :func:`export_evidence_packet` — the drafted instrument plus a numbered
    exhibit index (the IEP provision and the exact service-log entries) and the
    cited authorities, assembled into one document ready to send.

State-specific entries are marked ``verify_required`` — confirm the current form
and address on the state's site before filing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from . import corpus
from .analysis import CommitmentAnalysis
from .grounding import build_evidence_bundle
from .models import Instrument


@dataclass(frozen=True)
class FilingInfo:
    state: str
    agency_name: str
    how_to_file: str
    limitations_years: int = 2
    notes: str = ""
    verify_required: bool = False


# Federal floor for every state, plus a worked example. Add verified states over
# time — the federal process under 34 C.F.R. 300.151–300.153 applies everywhere.
_FEDERAL = FilingInfo(
    state="",
    agency_name="your State Education Agency (SEA), Special Education Division",
    how_to_file=(
        "File a signed, written state complaint with your State Education "
        "Agency's special-education division. Every state must have a complaint "
        "process under 34 C.F.R. §§ 300.151–300.153; find your state's current "
        "complaint form and mailing/upload address on its Department of "
        "Education special-education page. Send a copy to the school district."
    ),
    limitations_years=2,
    notes="Federal floor — localize to your state before filing.",
)

STATE_FILING = {
    "": _FEDERAL,
    "CA": FilingInfo(
        state="CA",
        agency_name="California Department of Education (CDE), Special "
                    "Education Division",
        how_to_file=(
            "Submit a written state complaint to the CDE Special Education "
            "Division. See the CDE 'Special Education Complaint Procedures' page "
            "for the current intake form and address, and copy your district."
        ),
        limitations_years=2,
        notes="Verify the current CDE form and address before filing.",
        verify_required=True,
    ),
}


def filing_instructions(state: str = "") -> FilingInfo:
    """Where/how to file, defaulting to the federal floor for unlisted states."""
    return STATE_FILING.get(state.upper(), _FEDERAL)


def _exhibit_lines(analyses: Sequence[CommitmentAnalysis]) -> List[str]:
    lines: List[str] = []
    n = 0
    for a in analyses:
        for v in a.violations:
            bundle = build_evidence_bundle(v)
            n += 1
            service = a.commitment.service_type.value.replace("_", " ")
            lines.append(f"Exhibit {n} — {service}: {v.type.value}")
            for ref in bundle.iep_refs:
                lines.append(f"    IEP: {ref.cite()}"
                             + (f"  {ref.uri}" if ref.uri else ""))
            if bundle.log_refs:
                dates = ", ".join(r.locator for r in bundle.log_refs if r.locator)
                lines.append(f"    Service-log entries: {dates}")
    return lines


def export_evidence_packet(
    instrument: Instrument,
    analyses: Sequence[CommitmentAnalysis],
    *,
    state: str = "",
    filename: Optional[str] = None,
) -> str:
    """Assemble the filable packet: cover, letter, exhibits, authorities, how-to.

    Returns the packet text; also writes it to ``filename`` when given.
    """
    info = filing_instructions(state)
    parts: List[str] = []
    parts.append("=" * 72)
    parts.append(f"EVIDENCE PACKET — {instrument.type.value}")
    parts.append("=" * 72)

    parts.append("\n--- WHERE TO FILE ---")
    parts.append(f"Agency: {info.agency_name}")
    parts.append(info.how_to_file)
    if info.verify_required:
        parts.append("(Verify the current form/address on the state's site.)")

    parts.append("\n--- THE COMPLAINT ---")
    parts.append(instrument.draft_text)

    parts.append("\n--- EXHIBIT INDEX ---")
    exhibits = _exhibit_lines(analyses)
    parts.extend(exhibits if exhibits else ["(attach the IEP and the service logs)"])

    parts.append("\n--- LEGAL AUTHORITIES ---")
    for cid in instrument.citations:
        if corpus.exists(cid):
            p = corpus.get(cid)
            line = f"  {p.short_label}: {p.governs}."
            if p.url:
                line += f" {p.url}"
            parts.append(line)

    text = "\n".join(parts)
    if filename:
        from pathlib import Path
        Path(filename).write_text(text, encoding="utf-8")
    return text
