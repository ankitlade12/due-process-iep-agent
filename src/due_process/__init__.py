"""Due Process — an IEP enforcement agent.

A grounded compliance agent that tracks whether a school delivers the
special-education services promised in a child's IEP, detects material failures
deterministically, computes the compensatory time owed, tracks the statute of
limitations, and drafts cited legal instruments with human approval.

The package is organized around a hard boundary between deterministic logic and
the LLM:

  * Deterministic, unit-tested core — :mod:`due_process.ledger`,
    :mod:`due_process.materiality`, :mod:`due_process.deadlines`,
    :mod:`due_process.pwn`. No LLM ever does the math or the law lookup.
  * Legal grounding — :mod:`due_process.corpus`, :mod:`due_process.grounding`.
    Every claim links to a verifiable source.

The bounded LLM layer (extraction, classification, drafting) sits on top and is
added separately so the core remains auditable on its own.
"""

__version__ = "0.1.0"
