"""Extract structured service commitments from IEP text.

A *bounded* LLM task: turn the messy free text of an IEP services page into
:class:`~due_process.models.ServiceCommitment` rows. Per the spec, the parsed
values are **always shown back to the parent to confirm** before they drive any
analysis (``needs_confirmation=True``) — extraction errors must never silently
become legal claims.

Offline, a regex parser handles clean, well-formed service lines. With a key, the
Qwen model handles district-format drift and prose. Either way the output is the
same structured object, gated behind human confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from ..models import (
    DeliverySetting,
    FrequencyPeriod,
    ServiceCommitment,
    ServiceLocation,
    ServiceType,
    SourceKind,
    SourceRef,
)
from .client import LLMClient

_SERVICE_KEYWORDS = [
    (("speech", "language", "slp"), ServiceType.SPEECH_LANGUAGE),
    (("occupational", "ot"), ServiceType.OCCUPATIONAL_THERAPY),
    (("physical therapy", "physical", "pt"), ServiceType.PHYSICAL_THERAPY),
    (("counsel", "psycholog", "social work"), ServiceType.COUNSELING),
    (("behavior", "aba"), ServiceType.BEHAVIORAL_SUPPORT),
    (("specialized instruction", "specially designed", "resource"),
     ServiceType.SPECIALIZED_INSTRUCTION),
]


@dataclass
class ExtractedCommitment:
    """A parsed commitment plus the provenance and confirmation flag."""

    commitment: ServiceCommitment
    confidence: float
    source_excerpt: str
    needs_confirmation: bool = True
    method: str = "rule_based"


def _service_type(text: str) -> Optional[ServiceType]:
    low = text.lower()
    for keywords, stype in _SERVICE_KEYWORDS:
        if any(k in low for k in keywords):
            return stype
    return None


def _parse_line(line: str, index: int, source_uri: str) -> Optional[ExtractedCommitment]:
    low = line.lower()

    # Match frequency, period, and duration independently so messy phrasings
    # like "3 x 30 minutes per week" or "30 min, 3 times weekly" all parse.
    freq_match = re.search(r"(\d+)\s*(?:x|×|times?|sessions?)\b", low)
    dur_match = re.search(r"(\d+)\s*(?:min\b|minute)", low)
    if not freq_match or not dur_match:
        return None

    stype = _service_type(line)
    if stype is None:
        return None

    period = FrequencyPeriod.WEEK  # IEP services are weekly by default
    period_match = re.search(
        r"per\s+(week|month)|/\s*(week|month|wk|mo)|\b(week|month)ly\b", low)
    if period_match:
        token = next(g for g in period_match.groups() if g)
        period = (FrequencyPeriod.MONTH
                  if token.startswith("mo") else FrequencyPeriod.WEEK)

    frequency_count = int(freq_match.group(1))
    duration = int(dur_match.group(1))

    setting = DeliverySetting.INDIVIDUAL
    if "group" in low:
        setting = DeliverySetting.GROUP

    location: Optional[ServiceLocation] = None
    if "pull" in low:
        location = ServiceLocation.PULL_OUT
    elif "push" in low:
        location = ServiceLocation.PUSH_IN

    group_size_max = None
    gmatch = re.search(r"(?:max|group of|up to)\s*(\d+)", low) or re.search(
        r"(\d+)\s*:\s*1", low)
    if gmatch:
        group_size_max = int(gmatch.group(1))

    commitment = ServiceCommitment(
        id=f"svc-{index + 1}",
        service_type=stype,
        frequency_count=frequency_count,
        frequency_period=period,
        duration_minutes=duration,
        setting=setting,
        location=location,
        group_size_max=group_size_max,
        source_ref=SourceRef(
            kind=SourceKind.IEP,
            locator=f"line {index + 1}",
            description=line.strip()[:120],
            uri=source_uri,
            record_id=f"svc-{index + 1}",
        ),
    )
    return ExtractedCommitment(
        commitment=commitment,
        confidence=0.85,
        source_excerpt=line.strip(),
        method="rule_based",
    )


def _rule_based(iep_text: str, source_uri: str) -> List[ExtractedCommitment]:
    results: List[ExtractedCommitment] = []
    # Services often live one-per-line or separated by semicolons.
    raw_lines = re.split(r"[\n;]+", iep_text)
    for line in raw_lines:
        if not line.strip():
            continue
        parsed = _parse_line(line, len(results), source_uri)
        if parsed is not None:
            results.append(parsed)
    return results


_SYSTEM = (
    "You extract special-education service commitments from the services page of "
    "an IEP. Return ONLY JSON: {\"commitments\": [ ... ]}. Each commitment has: "
    '"service_type" (speech_language|occupational_therapy|physical_therapy|'
    "counseling|behavioral_support|specialized_instruction|other), "
    '"frequency_count" (int), "frequency_period" (week|month), '
    '"duration_minutes" (int), "setting" (individual|group), '
    '"location" (pull_out|push_in|null), "group_size_max" (int|null), '
    '"provider_qualification" (string), "source_excerpt" (the exact text), '
    '"confidence" (0..1). Extract only what is written. Do not infer minutes or '
    "frequencies that are not stated."
)


def _coerce_commitment(obj: dict, index: int, source_uri: str
                       ) -> Optional[ExtractedCommitment]:
    try:
        stype = ServiceType(str(obj["service_type"]))
        period = FrequencyPeriod(str(obj["frequency_period"]))
        setting = DeliverySetting(str(obj.get("setting", "individual")))
    except (KeyError, ValueError):
        return None
    loc_raw = obj.get("location")
    location = None
    if loc_raw in ("pull_out", "push_in"):
        location = ServiceLocation(loc_raw)
    excerpt = str(obj.get("source_excerpt", "")).strip()
    commitment = ServiceCommitment(
        id=f"svc-{index + 1}",
        service_type=stype,
        frequency_count=int(obj["frequency_count"]),
        frequency_period=period,
        duration_minutes=int(obj["duration_minutes"]),
        setting=setting,
        location=location,
        group_size_max=obj.get("group_size_max"),
        provider_qualification=str(obj.get("provider_qualification", "")),
        source_ref=SourceRef(
            kind=SourceKind.IEP,
            locator="services page",
            description=excerpt[:120],
            uri=source_uri,
            record_id=f"svc-{index + 1}",
        ),
    )
    try:
        confidence = float(obj.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    return ExtractedCommitment(
        commitment=commitment, confidence=confidence,
        source_excerpt=excerpt, method="qwen",
    )


def _llm(iep_text: str, client: LLMClient, source_uri: str
         ) -> List[ExtractedCommitment]:
    try:
        data = client.complete_json(
            _SYSTEM, iep_text, model=client.config.workhorse_model
        )
    except Exception:
        return _rule_based(iep_text, source_uri)
    items = data.get("commitments", []) if isinstance(data, dict) else []
    results: List[ExtractedCommitment] = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        parsed = _coerce_commitment(obj, len(results), source_uri)
        if parsed is not None:
            results.append(parsed)
    # If the model returned nothing usable, fall back to rules.
    return results or _rule_based(iep_text, source_uri)


def extract_commitments(
    iep_text: str,
    *,
    client: Optional[LLMClient] = None,
    source_uri: str = "",
) -> List[ExtractedCommitment]:
    """Extract commitments from IEP text, flagged for human confirmation."""
    if client is not None and client.available:
        return _llm(iep_text, client, source_uri)
    return _rule_based(iep_text, source_uri)
