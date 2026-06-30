"""Classify a missed/short session's reason as excused vs unexcused.

This is a *bounded* LLM task: it maps a free-text reason to one of three labels —
``EXCUSED`` (attributable to the child/family or a universal closure),
``UNEXCUSED`` (the school failed to staff or schedule the service), or
``AMBIGUOUS``. Per the spec, an ambiguous reason is **never auto-resolved**; it is
flagged for a human. The deterministic ledger then sums according to the
confirmed labels — the LLM does not touch the minutes.

Two implementations share the interface: a transparent keyword classifier
(offline default, also a clean baseline) and a Qwen-backed classifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..models import ExcusedClass, LogStatus, ServiceLog
from .client import LLMClient

CONFIDENCE_THRESHOLD = 0.6

# Reasons attributable to the child/family or a universal closure -> excused.
# Subject-aware so "provider absent" does NOT match the child's absence here.
_EXCUSED_PATTERNS = [
    r"\bstudent\b.{0,20}\b(absent|out|sick|ill|illness)\b",
    r"\bchild\b.{0,20}\b(absent|out|sick|ill|illness)\b",
    r"\bout\s+sick\b",
    r"\b(illness|flu)\b",
    r"\bfamily\s+(emergency|vacation)\b",
    r"\bparent\s+(cancel|kept\s+home|declined)",
    r"\bvacation\b",
    r"\bsnow\s+day\b",
    r"\b(school\s+)?holiday\b",
    r"\bschool\s+closed\b",
    r"\bfield\s+trip\b",
    r"\bsuspended\b",
]

# A bare "absent"/"sick" (no subject) means the student, but only when no
# school-side cause is present — applied as a fallback in _rule_based.
_BARE_ABSENCE = re.compile(r"\b(absent|absence|sick|ill)\b")

# Reasons attributable to the school's failure to deliver -> unexcused.
_UNEXCUSED_PATTERNS = [
    r"\b(provider|therapist|slp|ot|pt|clinician|staff)\s+(was\s+)?(absent|out|sick|unavailable)\b",
    r"\bno\s+(substitute|sub|coverage|therapist|provider)\b",
    r"\b(short[-\s]?staffed|staffing|understaffed)\b",
    r"\b(vacancy|unfilled|position\s+open|no\s+one\s+hired)\b",
    r"\bnot\s+scheduled\b",
    r"\bscheduling\s+conflict\b",
    r"\bdouble[-\s]?booked\b",
    r"\broom\s+(unavailable|not\s+available|in\s+use)\b",
    r"\bforgot\b",
    r"\bcancel(l)?ed\s+by\s+(the\s+)?(school|provider|therapist|district)\b",
    r"\bservice\s+not\s+(provided|started|begun)\b",
]


@dataclass
class ReasonClassification:
    """One reason's classification with provenance for the human reviewer."""

    excused: ExcusedClass
    confidence: float
    rationale: str
    needs_human: bool
    method: str  # "rule_based" | "qwen"


@dataclass
class ClassificationOutcome:
    """Result of classifying a batch of logs."""

    review_items: List[ServiceLog] = field(default_factory=list)
    classifications: dict = field(default_factory=dict)  # log_id -> ReasonClassification

    @property
    def needs_human_count(self) -> int:
        return len(self.review_items)


def _rule_based(text: str) -> ReasonClassification:
    blob = (text or "").lower().strip()
    if not blob:
        return ReasonClassification(
            ExcusedClass.AMBIGUOUS, 0.5,
            "No reason text was recorded; a human must determine the cause.",
            needs_human=True, method="rule_based",
        )
    excused_hit = any(re.search(p, blob) for p in _EXCUSED_PATTERNS)
    unexcused_hit = any(re.search(p, blob) for p in _UNEXCUSED_PATTERNS)
    # A bare "absent"/"sick" with no school-side cause means the student.
    if not unexcused_hit and _BARE_ABSENCE.search(blob):
        excused_hit = True

    if excused_hit and not unexcused_hit:
        return ReasonClassification(
            ExcusedClass.EXCUSED, 0.9,
            "Reason matches a child/family or closure cause the school is not "
            "responsible for.",
            needs_human=False, method="rule_based",
        )
    if unexcused_hit and not excused_hit:
        return ReasonClassification(
            ExcusedClass.UNEXCUSED, 0.9,
            "Reason matches a school staffing/scheduling failure to deliver.",
            needs_human=False, method="rule_based",
        )
    if excused_hit and unexcused_hit:
        return ReasonClassification(
            ExcusedClass.AMBIGUOUS, 0.5,
            "Reason mentions both child-side and school-side causes; a human "
            "must decide which controls.",
            needs_human=True, method="rule_based",
        )
    return ReasonClassification(
        ExcusedClass.AMBIGUOUS, 0.5,
        "Reason does not clearly match an excused or unexcused cause.",
        needs_human=True, method="rule_based",
    )


_SYSTEM = (
    "You classify why a special-education service session was missed or cut "
    "short, for an IEP-compliance tool. Return ONLY JSON with keys: "
    '"label" (one of "excused", "unexcused", "ambiguous"), "confidence" '
    "(0..1), and \"rationale\" (one sentence). EXCUSED = the cause is the "
    "child/family or a universal school closure (student absent, illness, "
    "family vacation, snow day). UNEXCUSED = the school failed to deliver "
    "(provider absent with no substitute, unfilled position, not scheduled, "
    "scheduling conflict). If the cause is genuinely unclear, return "
    '"ambiguous" — do NOT guess. Never invent facts not in the text.'
)


def _llm(text: str, client: LLMClient, context: str = "") -> ReasonClassification:
    user = f"Reason text: {text!r}"
    if context:
        user += f"\nContext: {context}"
    try:
        data = client.complete_json(
            _SYSTEM, user, model=client.config.workhorse_model
        )
    except Exception:  # network/parse error -> safe fallback, flag for human
        rc = _rule_based(text)
        rc.rationale = f"(LLM unavailable; used rules) {rc.rationale}"
        return rc

    label = str(data.get("label", "ambiguous")).lower()
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    rationale = str(data.get("rationale", "")).strip()

    mapping = {
        "excused": ExcusedClass.EXCUSED,
        "unexcused": ExcusedClass.UNEXCUSED,
        "ambiguous": ExcusedClass.AMBIGUOUS,
    }
    excused = mapping.get(label, ExcusedClass.AMBIGUOUS)
    # Low confidence or an ambiguous label both route to a human.
    needs_human = (excused == ExcusedClass.AMBIGUOUS
                   or confidence < CONFIDENCE_THRESHOLD)
    if needs_human and excused != ExcusedClass.AMBIGUOUS:
        # Keep the model's leaning visible but do not auto-apply it.
        excused = ExcusedClass.AMBIGUOUS
    return ReasonClassification(
        excused=excused, confidence=confidence,
        rationale=rationale or "Classified by Qwen.",
        needs_human=needs_human, method="qwen",
    )


def classify_reason(
    text: str,
    *,
    client: Optional[LLMClient] = None,
    context: str = "",
) -> ReasonClassification:
    """Classify a single free-text reason.

    Uses Qwen when ``client`` is available, else the transparent keyword rules.
    """
    if client is not None and client.available:
        return _llm(text, client, context)
    return _rule_based(text)


def classify_logs(
    logs: List[ServiceLog],
    *,
    client: Optional[LLMClient] = None,
    reclassify: bool = False,
) -> ClassificationOutcome:
    """Classify the reasons on missed/short logs, in place.

    Sets ``log.excused`` for confidently-classified entries; leaves ambiguous
    entries as ``AMBIGUOUS`` and collects them for human review. Delivered logs
    and already-classified logs (unless ``reclassify``) are skipped.
    """
    outcome = ClassificationOutcome()
    for log in logs:
        if log.status not in (LogStatus.MISSED, LogStatus.SHORT):
            continue
        if not reclassify and log.excused not in (
            ExcusedClass.UNCLASSIFIED, ExcusedClass.AMBIGUOUS
        ):
            continue
        rc = classify_reason(log.missed_reason_text, client=client)
        outcome.classifications[log.id] = rc
        if rc.needs_human:
            log.excused = ExcusedClass.AMBIGUOUS
            outcome.review_items.append(log)
        else:
            log.excused = rc.excused
    return outcome
