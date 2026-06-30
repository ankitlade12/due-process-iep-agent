"""Evaluation harness: published precision/recall/FPR + citation accuracy.

This is the single move that beats every incumbent's unfalsifiable marketing:
report metrics on a labeled synthetic dataset, and show the grounded system's
false-positive rate and citation accuracy beating a raw-LLM baseline that has no
deterministic ledger and no grounding corpus.
"""

from .dataset import EvalCase, build_dataset
from .metrics import BinaryMetrics, binary_metrics, citation_validity, mae

__all__ = [
    "EvalCase",
    "build_dataset",
    "BinaryMetrics",
    "binary_metrics",
    "citation_validity",
    "mae",
]
