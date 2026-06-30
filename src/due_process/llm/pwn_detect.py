"""Detect which Prior Written Notice elements are present in a document.

This is the bounded-LLM half of the PWN check: it reads a PWN and decides, per
element, present or absent. The legal structure and the compliance verdict stay
in :mod:`due_process.pwn` (deterministic) — this only fills the checklist.

Offline, a keyword heuristic stands in; with a key, Qwen reads the document. PII
is redacted before any cloud call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from ..privacy import Redactor, redact_for_cloud
from .client import LLMClient

# Indicative phrases per element (34 C.F.R. 300.503(b)(1)-(7)).
_KEYWORDS = {
    1: [r"propos", r"refus", r"declin", r"will (change|implement|provide|"
        r"discontinue|reduce|increase)", r"intend to"],
    2: [r"because", r"\breason", r"based on", r"in order to", r"the basis for"],
    3: [r"evaluation", r"assessment", r"\breport", r"\bdata\b", r"observation",
        r"\btest", r"progress (report|data)", r"records"],
    4: [r"procedural safeguard", r"your rights", r"copy of (the|these)",
        r"safeguards notice", r"protection under"],
    5: [r"contact", r"assistance in understanding", r"parent (training|center|"
        r"information)", r"advoca", r"resources"],
    6: [r"other option", r"alternativ", r"options (the team )?considered",
        r"reject"],
    7: [r"other (relevant )?factor", r"also considered", r"additional factor"],
}


@dataclass
class PwnDetection:
    present_by_element: Dict[int, bool] = field(default_factory=dict)
    method: str = "rule_based"


def _rule_based(text: str) -> PwnDetection:
    low = (text or "").lower()
    present = {n: any(re.search(p, low) for p in pats)
               for n, pats in _KEYWORDS.items()}
    return PwnDetection(present_by_element=present, method="rule_based")


_SYSTEM = (
    "You check a special-education Prior Written Notice for the seven required "
    "elements under 34 C.F.R. 300.503(b). Return ONLY JSON mapping \"1\"..\"7\" "
    "to true/false: (1) a description of the action proposed or refused; (2) an "
    "explanation of why; (3) the evaluations/records relied on; (4) a statement "
    "of procedural safeguards and how to get a copy; (5) sources of assistance "
    "for the parent; (6) other options considered and why rejected; (7) other "
    "relevant factors. Mark true only if the element is actually present."
)


def _llm(text: str, client: LLMClient) -> PwnDetection:
    try:
        data = client.complete_json(_SYSTEM, text,
                                    model=client.config.workhorse_model)
    except Exception:
        return _rule_based(text)
    present = {}
    for n in range(1, 8):
        present[n] = bool(data.get(str(n), data.get(n, False)))
    return PwnDetection(present_by_element=present, method="qwen")


def detect_pwn_elements(
    text: str,
    *,
    client: Optional[LLMClient] = None,
    redactor: Optional[Redactor] = None,
) -> PwnDetection:
    """Detect which of the seven PWN elements appear in the document."""
    if client is not None and client.available:
        return _llm(redact_for_cloud(text, redactor), client)
    return _rule_based(text)
