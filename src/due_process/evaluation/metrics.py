"""Metrics for the evaluation.

The numbers that matter most for this product:

  * **False-positive rate** — telling a parent they have a case when they do not
    is the worst failure, so it is reported prominently.
  * **Citation accuracy** — the share of cited authorities that actually resolve
    to a real provision in the corpus (a hallucinated cite is worse than none).
  * Precision / recall / F1 on material-failure detection, and
  * mean absolute error on compensatory minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .. import corpus


@dataclass
class BinaryMetrics:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_positive_rate(self) -> float:
        denom = self.fp + self.tn
        return self.fp / denom if denom else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.tn + self.fn
        return (self.tp + self.tn) / total if total else 0.0


def binary_metrics(labels: Sequence[bool], preds: Sequence[bool]) -> BinaryMetrics:
    if len(labels) != len(preds):
        raise ValueError("labels and preds must be the same length")
    tp = fp = tn = fn = 0
    for label, pred in zip(labels, preds):
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
        elif not pred and not label:
            tn += 1
        else:
            fn += 1
    return BinaryMetrics(tp=tp, fp=fp, tn=tn, fn=fn)


def citation_validity(cited_ids: Sequence[str]) -> tuple[int, int]:
    """Return (valid, total): how many cited ids resolve to a real provision."""
    total = len(cited_ids)
    valid = sum(1 for cid in cited_ids if corpus.exists(cid))
    return valid, total


def citation_accuracy(cited_ids: Sequence[str]) -> float:
    valid, total = citation_validity(cited_ids)
    return valid / total if total else 0.0


def mae(true: Sequence[int], pred: Sequence[int]) -> float:
    if len(true) != len(pred):
        raise ValueError("true and pred must be the same length")
    if not true:
        return 0.0
    return sum(abs(t - p) for t, p in zip(true, pred)) / len(true)
