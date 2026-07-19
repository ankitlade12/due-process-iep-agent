"""The human-in-the-loop approval gate.

An instrument is drafted in ``DRAFT`` status. It cannot be recorded as sent until
a human approves it (``APPROVED``), and only then can it be marked ``SENT`` with
a timestamp. This is the Track 4 "human checkpoint at every critical decision"
made concrete: the agent can prepare, but a person authorizes every outbound act.
The state transition records a delivery performed by a caller; it does not itself
transmit a document.
"""

from __future__ import annotations

from datetime import datetime

from ..models import Instrument, InstrumentStatus


class ApprovalError(RuntimeError):
    """Raised on an illegal status transition (e.g. send before approve)."""


def approve(instrument: Instrument) -> Instrument:
    """Mark a drafted instrument as approved by the human reviewer."""
    if instrument.status == InstrumentStatus.SENT:
        raise ApprovalError("Cannot approve an instrument that was already sent.")
    instrument.status = InstrumentStatus.APPROVED
    return instrument


def send(instrument: Instrument, sent_at: datetime) -> Instrument:
    """Record delivery already performed by an authorized external adapter.

    This function performs no network, email, or filing operation. Refusing to
    record delivery before approval is the core safety property. ``sent_at`` is
    passed in so the audit trail is reproducible.
    """
    if instrument.status != InstrumentStatus.APPROVED:
        raise ApprovalError(
            "Instrument must be APPROVED by a human before it can be sent "
            f"(current status: {instrument.status.value})."
        )
    instrument.status = InstrumentStatus.SENT
    instrument.sent_timestamp = sent_at
    return instrument


def reset_to_draft(instrument: Instrument) -> Instrument:
    """Return an instrument to draft (e.g. the reviewer requested edits)."""
    if instrument.status == InstrumentStatus.SENT:
        raise ApprovalError("Cannot edit an instrument that was already sent.")
    instrument.status = InstrumentStatus.DRAFT
    return instrument
