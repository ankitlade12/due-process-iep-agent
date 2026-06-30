"""The baseline: violation detection with no ledger and no grounding corpus.

This is the contrast that makes the grounded system's numbers mean something.
Two baselines share an interface:

  * ``HeuristicBaseline`` — offline, reproducible. It flags a material failure
    whenever there is *any* unexcused shortfall (no threshold) and cites law the
    ungrounded way a naive tool would, which does not validate. It exists to make
    the eval runnable with no key while still demonstrating the failure modes the
    grounding layer fixes: over-flagging (high FPR) and unverifiable citations.
  * ``QwenBaseline`` — raw Qwen prompted to judge material failure and cite the
    law from memory, with no deterministic ledger and no corpus. Used when a key
    is configured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..ledger import compute_ledger
from ..llm.client import LLMClient
from .dataset import EvalCase

# Map a free-text citation a model might emit to a corpus id, giving the baseline
# fair credit when it happens to cite a real, on-point authority.
_CITATION_PATTERNS = [
    (r"300\.323", "cfr_300_323"),
    (r"300\.320", "cfr_300_320"),
    (r"300\.503", "cfr_300_503"),
    (r"300\.15[123]", "cfr_300_151_153"),
    (r"1415", "usc_1415_sol"),
    (r"1401", "usc_1401_9"),
    (r"1412", "usc_1412_a_1"),
    (r"van\s*duyn", "van_duyn"),
    (r"endrew", "endrew_f"),
    (r"reid", "reid_v_dc"),
]


def match_citation(text: str) -> Optional[str]:
    low = text.lower()
    for pattern, cid in _CITATION_PATTERNS:
        if re.search(pattern, low):
            return cid
    return None


@dataclass
class BaselinePrediction:
    material: bool
    matched_ids: List[str] = field(default_factory=list)   # cites that resolve
    raw_citations: List[str] = field(default_factory=list)  # everything cited
    method: str = ""


class HeuristicBaseline:
    """Offline baseline: no materiality threshold, no grounding."""

    name = "heuristic (no ledger, no grounding)"
    available = True

    def predict(self, case: EvalCase) -> BaselinePrediction:
        ledger = compute_ledger(
            case.commitment, case.logs,
            window_start=case.window_start, window_end=case.window_end,
            instructional_periods=case.periods,
        )
        material = ledger.unexcused_shortfall_minutes > 0  # over-flags by design
        raw = ["IDEA (generally)", "Section 504"] if material else []
        matched = [cid for cid in (match_citation(c) for c in raw) if cid]
        return BaselinePrediction(material=material, matched_ids=matched,
                                  raw_citations=raw, method=self.name)


_SYSTEM = (
    "You are evaluating whether a school materially failed to implement a "
    "student's IEP service, from memory, with no tools. Return ONLY JSON: "
    '{"material_failure": true|false, "citations": ["..."]}. Cite the specific '
    "IDEA statutes/regulations or cases you would rely on."
)


class QwenBaseline:
    """Online baseline: raw Qwen, no ledger, no corpus."""

    name = "raw Qwen (no ledger, no grounding)"

    def __init__(self, client: LLMClient):
        self.client = client
        self.available = client.available

    def predict(self, case: EvalCase) -> BaselinePrediction:
        delivered = sum(1 for l in case.logs if l.minutes_delivered > 0)
        missed = sum(1 for l in case.logs if l.minutes_delivered == 0)
        required = case.commitment.frequency_count * case.periods
        facts = (
            f"IEP requires {case.commitment.service_type.value} "
            f"{case.commitment.frequency_count}x/week, "
            f"{case.commitment.duration_minutes} min, over {case.periods} weeks "
            f"({required} sessions). Logs: {delivered} delivered, {missed} "
            "missed (mix of student absences and provider absences). Was there a "
            "material failure to implement? Cite the governing law."
        )
        try:
            data = self.client.complete_json(
                _SYSTEM, facts, model=self.client.config.orchestrator_model)
        except Exception:
            return HeuristicBaseline().predict(case)
        material = bool(data.get("material_failure", False))
        raw = [str(c) for c in data.get("citations", [])]
        matched = [cid for cid in (match_citation(c) for c in raw) if cid]
        return BaselinePrediction(material=material, matched_ids=matched,
                                  raw_citations=raw, method=self.name)


def get_baseline(client: Optional[LLMClient]):
    """Qwen baseline when a key is available, else the offline heuristic."""
    if client is not None and client.available:
        return QwenBaseline(client)
    return HeuristicBaseline()
