"""Synthetic policy-regression verification and exploratory contrast fixtures.

The package checks deterministic behavior on constructed scenarios. It does not
contain an independently labeled representative dataset and therefore does not
publish real-world accuracy, precision, recall, or false-positive estimates.
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
