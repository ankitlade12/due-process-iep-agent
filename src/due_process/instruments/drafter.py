"""Draft the outbound instruments.

The legal scaffolding and citations of every letter are fixed by this module and
validated against the corpus; only the factual narrative is written by the LLM
(or its template fallback). Each function returns an :class:`Instrument` in
``DRAFT`` status — never sent until a human approves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence

from .. import corpus
from ..analysis import CommitmentAnalysis
from ..grounding import EvidenceBundle
from ..llm.client import LLMClient
from ..llm.narrative import summarize_pattern
from ..models import (
    Instrument,
    InstrumentStatus,
    InstrumentType,
    ServiceCommitment,
    SourceRef,
)
from ..systemic import SystemicFinding

_DISCLAIMER = (
    "This document is information and drafting support prepared with the "
    "assistance of an automated tool. It is not legal advice. Please review it "
    "for accuracy before sending."
)


@dataclass
class LetterContext:
    """The case identifiers used to fill a letter. Defaults are placeholders so
    no personally identifiable information is required to produce a draft."""

    student_name: str = "[Student Name]"
    parent_name: str = "[Parent/Guardian Name]"
    school_name: str = "[School Name]"
    district_name: str = "[School District]"
    state: str = ""
    state_agency_name: str = "[State Education Agency]"
    letter_date: Optional[date] = None
    case_id: str = ""


def _fmt_date(d: Optional[date]) -> str:
    return d.isoformat() if d else "[Date]"


def _citation_block(ids: Sequence[str]) -> str:
    seen: List[str] = []
    for cid in ids:
        if cid not in seen and corpus.exists(cid):
            seen.append(cid)
    lines = ["Legal authorities cited:"]
    for cid in seen:
        p = corpus.get(cid)
        line = f"  - {p.short_label}: {p.governs}."
        if p.url:
            line += f" {p.url}"
        if p.verify_required:
            line += " (verify against primary source)"
        lines.append(line)
    return "\n".join(lines)


def _list_dates(refs: Sequence[SourceRef], limit: int = 12) -> str:
    locators = [r.locator for r in refs if r.locator]
    if not locators:
        return "(see attached service logs)"
    shown = locators[:limit]
    extra = len(locators) - len(shown)
    tail = f", and {extra} more" if extra > 0 else ""
    return ", ".join(shown) + tail


def draft_service_log_request(
    commitments: Sequence[ServiceCommitment],
    context: LetterContext,
    *,
    window_start: date,
    window_end: date,
    client: Optional[LLMClient] = None,
) -> Instrument:
    """Request the complete service-delivery records — the first move when logs
    are incomplete (you cannot prove a shortfall you have not documented)."""
    services = "\n".join(
        f"  - {c.service_type.value.replace('_', ' ')}: "
        f"{c.frequency_count}x/{c.frequency_period.value}, "
        f"{c.duration_minutes} min ({c.setting.value})"
        for c in commitments
    )
    citations = ["cfr_300_613", "cfr_part_99"]
    body = "\n\n".join([
        _fmt_date(context.letter_date),
        f"From: {context.parent_name}\nTo: {context.school_name}, "
        f"{context.district_name}",
        f"Re: Request to inspect special-education service records for "
        f"{context.student_name}",
        "Under my right to inspect and review my child's education records "
        "(34 C.F.R. § 300.613; FERPA, 34 C.F.R. Part 99), I request the "
        "complete service-delivery logs for the following IEP services for the "
        f"period {window_start.isoformat()} to {window_end.isoformat()}:",
        services,
        "For each scheduled session, please include: the date, the minutes "
        "delivered, the setting (individual or group, and group size), the "
        "provider, and the documented reason for any missed or shortened "
        "session.",
        "Please provide these records without unnecessary delay and, in any "
        "event, within 45 days of this request and before any scheduled IEP "
        "meeting, as required by 34 C.F.R. § 300.613.",
        f"Respectfully,\n{context.parent_name}",
        _citation_block(citations),
        _DISCLAIMER,
    ])
    return Instrument(
        type=InstrumentType.SERVICE_LOG_REQUEST,
        violation_ids=[],
        draft_text=body,
        citations=citations,
        status=InstrumentStatus.DRAFT,
    )


def draft_state_complaint(
    analyses: Sequence[CommitmentAnalysis],
    context: LetterContext,
    *,
    client: Optional[LLMClient] = None,
) -> Instrument:
    """Draft a state complaint (34 C.F.R. 300.151-300.153) from the analyses.

    The narrative restates the deterministic findings; the legal structure,
    standard, and relief framing are fixed and cited.
    """
    violation_ids: List[str] = []
    citations: List[str] = [
        "cfr_300_151_153", "cfr_300_153", "cfr_300_323", "cfr_300_320",
        "usc_1401_9", "usc_1412_a_1", "van_duyn", "reid_v_dc",
    ]
    total_comp = 0
    facts_sections: List[str] = []
    earliest_deadline: Optional[date] = None

    for a in analyses:
        narrative = summarize_pattern(a, client=client, style="formal")
        facts_sections.append(narrative)
        for v, bundle in zip(a.violations, a.bundles):
            violation_ids.append(v.id)
            citations.extend(v.legal_refs)
            facts_sections.append(
                f"  Evidence ({v.type.value}): IEP {_bundle_iep(bundle)}; "
                f"service-log entries on {_list_dates(bundle.log_refs)}."
            )
        if a.compensatory:
            total_comp += a.compensatory.estimated_minutes
        for clock in a.deadlines:
            if earliest_deadline is None or clock.sol_expiry_date < earliest_deadline:
                earliest_deadline = clock.sol_expiry_date

    relief = "\n".join([
        "  1. A finding that the district failed to implement the IEP as "
        "written, denying a free appropriate public education.",
        f"  2. Compensatory services of approximately {total_comp} minutes "
        f"({total_comp / 60:.1f} hours) as an equitable starting position under "
        "Reid v. District of Columbia, subject to a qualitative analysis rather "
        "than a mechanical hour-for-hour award.",
        "  3. Corrective action to ensure the services are delivered going "
        "forward.",
    ])

    timeliness = (
        "Each violation alleged occurred within the one year preceding this "
        "complaint, as required by 34 C.F.R. § 300.153(c)."
    )
    if earliest_deadline:
        timeliness += (f" The earliest events under review age out of the "
                       f"one-year window on {earliest_deadline.isoformat()}; "
                       "a due-process complaint remains available for two years.")

    body = "\n\n".join([
        _fmt_date(context.letter_date),
        f"From: {context.parent_name}\nTo: {context.state_agency_name}; "
        f"copy to {context.district_name}, {context.school_name}",
        f"Re: State Complaint under IDEA — {context.student_name}",
        "I. Nature of the Complaint\n"
        "This is a state complaint under 34 C.F.R. §§ 300.151–300.153 "
        "alleging that the district failed to implement the student's IEP as "
        "written, in violation of 34 C.F.R. § 300.323 and the obligation to "
        "provide a free appropriate public education under 20 U.S.C. "
        "§§ 1401(9) and 1412(a)(1).",
        "II. The Delivery Shortfall\n" + "\n\n".join(facts_sections),
        "III. Why This Is a Material Failure\n"
        "Under the material-failure-to-implement standard (Van Duyn v. Baker "
        "Sch. Dist.), a school's failure to implement a material portion of the "
        "IEP denies FAPE. The shortfall documented above crosses that threshold "
        "on the records cited.",
        "IV. Relief Requested\n" + relief,
        "V. Timeliness\n" + timeliness,
        f"Respectfully,\n{context.parent_name}",
        _citation_block(citations),
        _DISCLAIMER,
    ])
    return Instrument(
        type=InstrumentType.STATE_COMPLAINT,
        violation_ids=violation_ids,
        draft_text=body,
        citations=list(dict.fromkeys(citations)),
        status=InstrumentStatus.DRAFT,
    )


def draft_systemic_complaint(
    findings: Sequence[SystemicFinding],
    context: LetterContext,
    *,
    client: Optional[LLMClient] = None,
) -> Instrument:
    """Draft a district-wide *systemic* state complaint (34 C.F.R. 300.151(b)).

    Reports aggregate, de-identified patterns — counts and minute totals across
    many students, never an individual record. A systemic finding obligates the
    state agency to order district-wide relief, fixing services for every
    affected child rather than one at a time.
    """
    citations: List[str] = [
        "cfr_300_151_153", "cfr_300_323", "cfr_300_320",
        "usc_1401_9", "usc_1412_a_1", "van_duyn", "reid_v_dc",
    ]
    total_comp = 0
    sections: List[str] = []
    for f in findings:
        citations.extend(f.legal_refs)
        total_comp += f.total_compensatory_minutes
        service = f.service_type.value.replace("_", " ")
        sections.append(
            f"  - {service}: of {f.n_students_with_service} students receiving "
            f"this service in {f.district}, {f.n_students_material} "
            f"({f.material_student_share:.0%}) experienced a material failure to "
            f"implement. Aggregate unexcused shortfall: {f.total_unexcused_minutes} "
            f"minutes ({f.aggregate_shortfall_pct:.1%} of required service time). "
            f"(Reported only because at least {f.k_threshold} students are "
            f"affected; no individual student is identified.)"
        )

    body = "\n\n".join([
        _fmt_date(context.letter_date),
        f"From: {context.parent_name}\nTo: {context.state_agency_name}; "
        f"copy to {context.district_name}",
        f"Re: Systemic State Complaint under IDEA — {context.district_name}",
        "I. Nature of the Complaint\n"
        "This is a state complaint under 34 C.F.R. §§ 300.151–300.153. It alleges "
        "a systemic failure to implement IEPs across the district. Under 34 "
        "C.F.R. § 300.151(b), where a complaint alleges a failure that affects "
        "multiple children, the state education agency must resolve the systemic "
        "issue, not merely the individual case.",
        "II. The District-Wide Pattern (de-identified)\n" + "\n\n".join(sections),
        "III. Why This Is a Material, Systemic Failure\n"
        "The aggregate shortfalls above are computed from service-delivery "
        "records under the material-failure-to-implement standard (Van Duyn v. "
        "Baker Sch. Dist.). The breadth across students establishes a systemic, "
        "not isolated, failure.",
        "IV. Relief Requested\n"
        "  1. A finding of systemic failure to implement IEPs district-wide.\n"
        "  2. District-wide corrective action (staffing, scheduling, and "
        "monitoring) to prevent recurrence.\n"
        f"  3. Compensatory services for all affected students, an aggregate "
        f"equitable starting position of approximately {total_comp} minutes "
        f"({total_comp / 60:.1f} hours) under Reid v. District of Columbia.",
        f"Respectfully,\n{context.parent_name}",
        _citation_block(citations),
        _DISCLAIMER,
    ])
    return Instrument(
        type=InstrumentType.SYSTEMIC_COMPLAINT,
        violation_ids=[],
        draft_text=body,
        citations=list(dict.fromkeys(citations)),
        status=InstrumentStatus.DRAFT,
    )


def draft_pwn_request(
    context: LetterContext,
    *,
    proposed_change: str = "the change to my child's services",
    missing_elements: Optional[Sequence[str]] = None,
    client: Optional[LLMClient] = None,
) -> Instrument:
    """Request Prior Written Notice, optionally citing elements a prior PWN
    omitted (34 C.F.R. 300.503)."""
    citations = ["cfr_300_503"]
    note = ""
    if missing_elements:
        note = (
            "\n\nA prior notice did not contain all required elements. Please "
            "ensure the notice includes, in particular: "
            + "; ".join(missing_elements) + "."
        )
    body = "\n\n".join([
        _fmt_date(context.letter_date),
        f"From: {context.parent_name}\nTo: {context.school_name}, "
        f"{context.district_name}",
        f"Re: Request for Prior Written Notice — {context.student_name}",
        f"Under 34 C.F.R. § 300.503, I request Prior Written Notice "
        f"regarding {proposed_change}. The notice must contain all seven "
        "required elements: (1) a description of the action proposed or "
        "refused; (2) an explanation of why; (3) the evaluations/records relied "
        "on; (4) a statement of procedural safeguards and how to obtain a copy; "
        "(5) sources of assistance; (6) other options considered and why they "
        "were rejected; and (7) other relevant factors." + note,
        f"Respectfully,\n{context.parent_name}",
        _citation_block(citations),
        _DISCLAIMER,
    ])
    return Instrument(
        type=InstrumentType.PWN_REQUEST,
        violation_ids=[],
        draft_text=body,
        citations=citations,
        status=InstrumentStatus.DRAFT,
    )


def _bundle_iep(bundle: EvidenceBundle) -> str:
    if bundle.iep_refs:
        return bundle.iep_refs[0].cite()
    return "service line"
