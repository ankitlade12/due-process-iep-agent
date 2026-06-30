"""Instrument drafting with fixed legal scaffolding and human approval.

Each instrument (service-log request, state complaint, PWN request) is a fixed
legal template: the structure, the legal basis, and the citations are set by code
and validated against :mod:`due_process.corpus`. The LLM fills only the factual
narrative. Nothing is sent without passing through the human approval gate in
:mod:`due_process.instruments.approval`.
"""

from .approval import ApprovalError, approve, reset_to_draft, send
from .drafter import (
    LetterContext,
    draft_pwn_request,
    draft_service_log_request,
    draft_state_complaint,
    draft_systemic_complaint,
)

__all__ = [
    "LetterContext",
    "draft_service_log_request",
    "draft_state_complaint",
    "draft_systemic_complaint",
    "draft_pwn_request",
    "approve",
    "send",
    "reset_to_draft",
    "ApprovalError",
]
