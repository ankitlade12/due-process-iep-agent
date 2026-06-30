"""Plain-language summary and the factual narrative for letters.

The LLM writes the *narrative* — the human-readable description of what the
numbers show — and nothing else. The legal scaffolding and citations are fixed by
the instrument templates in :mod:`due_process.instruments`; the math is fixed by
the deterministic core. So this module is constrained to restating facts it is
handed: it must not state legal conclusions, cite law, or invent numbers.

A deterministic template renders the same paragraph offline; Qwen makes it read
more naturally when a key is present.
"""

from __future__ import annotations

import json
from typing import Optional

from ..analysis import CommitmentAnalysis
from .client import LLMClient


def _facts(analysis: CommitmentAnalysis) -> dict:
    led = analysis.ledger
    c = analysis.commitment
    loc = f" {c.location.value.replace('_', '-')}" if c.location else ""
    return {
        "service": c.service_type.value.replace("_", " "),
        "frequency_count": c.frequency_count,
        "frequency_period": c.frequency_period.value,
        "duration_minutes": c.duration_minutes,
        "setting": c.setting.value + loc,
        "window_start": led.window_start.isoformat(),
        "window_end": led.window_end.isoformat(),
        "required_sessions": led.required_sessions,
        "required_minutes": led.required_minutes,
        "delivered_sessions": led.delivered_sessions,
        "delivered_minutes": led.delivered_minutes,
        "excused_sessions": led.excused_sessions,
        "unexcused_sessions": led.unexcused_missed_sessions,
        "unexcused_minutes": led.unexcused_shortfall_minutes,
        "shortfall_pct": f"{led.shortfall_pct:.1%}",
        "is_material": analysis.materiality.is_material,
        "logs_complete": led.logs_complete,
    }


def _template_formal(f: dict) -> str:
    return (
        f"The student's IEP requires {f['service']} services "
        f"{f['frequency_count']} time(s) per {f['frequency_period']} for "
        f"{f['duration_minutes']} minutes per session ({f['setting']}). "
        f"Over the period from {f['window_start']} to {f['window_end']}, this "
        f"amounted to {f['required_sessions']} required sessions "
        f"({f['required_minutes']} minutes). The service logs show "
        f"{f['delivered_sessions']} sessions ({f['delivered_minutes']} minutes) "
        f"delivered. {f['excused_sessions']} session(s) were missed due to "
        f"excused absences. The remaining {f['unexcused_sessions']} session(s) "
        f"({f['unexcused_minutes']} minutes), or {f['shortfall_pct']} of the "
        f"required service time, were not delivered for reasons attributable to "
        f"the school."
    )


def _template_plain(f: dict) -> str:
    head = (
        f"Between {f['window_start']} and {f['window_end']}, your child's IEP "
        f"called for {f['required_sessions']} {f['service']} sessions. The "
        f"school's logs show {f['delivered_sessions']} were given."
    )
    if f["unexcused_minutes"] > 0:
        head += (
            f" After setting aside {f['excused_sessions']} that your child "
            f"missed for excused reasons, {f['unexcused_sessions']} sessions "
            f"({f['unexcused_minutes']} minutes, about {f['shortfall_pct']} of "
            f"the year) were missed because of the school."
        )
    else:
        head += " The school delivered what the IEP promised."
    return head


_SYSTEM = (
    "You write ONE factual paragraph for an IEP service-delivery matter. Use "
    "ONLY the numbers in the provided JSON. Do NOT state legal conclusions, do "
    "NOT cite statutes or cases (the document template adds citations "
    "separately), and do NOT invent any number or fact. Plain, precise, neutral."
)


def _llm(f: dict, client: LLMClient, style: str) -> str:
    audience = ("a parent, in plain language" if style == "plain"
                else "a formal complaint, in precise language")
    user = (
        f"Write the paragraph for {audience}. Facts (JSON):\n"
        f"{json.dumps(f, indent=2)}"
    )
    try:
        result = client.complete(_SYSTEM, user,
                                 model=client.config.orchestrator_model)
        text = result.text.strip()
        return text or (_template_plain(f) if style == "plain"
                        else _template_formal(f))
    except Exception:
        return _template_plain(f) if style == "plain" else _template_formal(f)


def summarize_pattern(
    analysis: CommitmentAnalysis,
    *,
    client: Optional[LLMClient] = None,
    style: str = "plain",
) -> str:
    """A one-paragraph description of the delivery pattern.

    ``style="plain"`` for a parent-facing summary, ``"formal"`` for letter prose.
    """
    f = _facts(analysis)
    if client is not None and client.available:
        return _llm(f, client, style)
    return _template_plain(f) if style == "plain" else _template_formal(f)
