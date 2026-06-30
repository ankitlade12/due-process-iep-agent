"""The legal grounding corpus.

This is the backbone of the grounding layer. Every legal claim the agent makes
must reference one of these provisions by id. Hallucination is prevented *by
construction*: :func:`due_process.grounding` validates that every citation
resolves to an entry here, so the model cannot assert a legal standard that is
not in this corpus.

Provenance (per the spec, ``idea1-iep-enforcement-agent.md``):
  * CFR / U.S.C. sections were verified against the eCFR (ecfr.gov) and the
    Cornell Legal Information Institute (law.cornell.edu). ``verify_required`` is
    ``False`` for those.
  * Case citations are from established special-education law and are marked
    ``verify_required = True`` — confirm against primary sources and localize per
    state before relying on them.

This is the *federal floor only*. States add their own timelines and procedures,
so a deployment must extend the corpus per state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class AuthorityKind(str, Enum):
    REGULATION = "regulation"  # Code of Federal Regulations
    STATUTE = "statute"        # United States Code
    CASE = "case"              # case law


@dataclass(frozen=True)
class LegalProvision:
    """One citable legal authority."""

    id: str
    short_label: str       # e.g. "34 C.F.R. § 300.323"
    citation: str          # full citation
    kind: AuthorityKind
    governs: str           # what it governs (the spec's "Governs" column)
    agent_use: str         # how the agent uses it (the spec's "How ... uses it")
    url: str = ""
    verify_required: bool = False

    def cite(self) -> str:
        """Citation string for letters and the UI."""
        return self.short_label

    def cite_full(self) -> str:
        return self.citation


# Cornell LII base URLs — stable and canonical.
def _cfr(section: str) -> str:
    return f"https://www.law.cornell.edu/cfr/text/34/{section}"


def _usc(section: str, fragment: str = "") -> str:
    base = f"https://www.law.cornell.edu/uscode/text/20/{section}"
    return f"{base}#{fragment}" if fragment else base


_PROVISIONS: List[LegalProvision] = [
    # ---- The umbrella right -------------------------------------------------
    LegalProvision(
        id="usc_1401_9",
        short_label="20 U.S.C. § 1401(9)",
        citation="20 U.S.C. § 1401(9)",
        kind=AuthorityKind.STATUTE,
        governs="Definition of a free appropriate public education (FAPE)",
        agent_use="The umbrella right the whole analysis rests on.",
        url=_usc("1401", "9"),
    ),
    LegalProvision(
        id="cfr_300_17",
        short_label="34 C.F.R. § 300.17",
        citation="34 C.F.R. § 300.17",
        kind=AuthorityKind.REGULATION,
        governs="Definition of FAPE (regulatory)",
        agent_use="Regulatory statement of the FAPE right.",
        url=_cfr("300.17"),
    ),
    LegalProvision(
        id="usc_1412_a_1",
        short_label="20 U.S.C. § 1412(a)(1)",
        citation="20 U.S.C. § 1412(a)(1)",
        kind=AuthorityKind.STATUTE,
        governs="State duty to make FAPE available",
        agent_use="Establishes the obligation being enforced.",
        url=_usc("1412"),
    ),
    # ---- IEP content & process ---------------------------------------------
    LegalProvision(
        id="cfr_300_320",
        short_label="34 C.F.R. § 300.320",
        citation="34 C.F.R. § 300.320",
        kind=AuthorityKind.REGULATION,
        governs="IEP content, including the statement of services with "
                "frequency, duration, and location",
        agent_use="Source for parsing the service commitments.",
        url=_cfr("300.320"),
    ),
    LegalProvision(
        id="cfr_300_321",
        short_label="34 C.F.R. § 300.321",
        citation="34 C.F.R. § 300.321",
        kind=AuthorityKind.REGULATION,
        governs="IEP Team composition",
        agent_use="Checking who was required at a meeting.",
        url=_cfr("300.321"),
    ),
    LegalProvision(
        id="cfr_300_322",
        short_label="34 C.F.R. § 300.322",
        citation="34 C.F.R. § 300.322",
        kind=AuthorityKind.REGULATION,
        governs="Parent participation in meetings",
        agent_use="Procedural rights reference.",
        url=_cfr("300.322"),
    ),
    LegalProvision(
        id="cfr_300_323",
        short_label="34 C.F.R. § 300.323(a),(c)",
        citation="34 C.F.R. § 300.323(a), (c)",
        kind=AuthorityKind.REGULATION,
        governs="IEP in effect at the start of the year; no delay in "
                "implementation",
        agent_use="The core implementation duty delivery is checked against.",
        url=_cfr("300.323"),
    ),
    LegalProvision(
        id="cfr_300_324",
        short_label="34 C.F.R. § 300.324(b)",
        citation="34 C.F.R. § 300.324(b)",
        kind=AuthorityKind.REGULATION,
        governs="Periodic review and revision of the IEP",
        agent_use="Timing of reviews.",
        url=_cfr("300.324"),
    ),
    LegalProvision(
        id="cfr_300_300",
        short_label="34 C.F.R. § 300.300",
        citation="34 C.F.R. § 300.300",
        kind=AuthorityKind.REGULATION,
        governs="Parental consent",
        agent_use="Consent and revocation handling.",
        url=_cfr("300.300"),
    ),
    # ---- Notices, evaluations, dispute resolution ---------------------------
    LegalProvision(
        id="cfr_300_502",
        short_label="34 C.F.R. § 300.502",
        citation="34 C.F.R. § 300.502",
        kind=AuthorityKind.REGULATION,
        governs="Independent Educational Evaluation (IEE) at public expense",
        agent_use="Instrument when the parent disputes the school evaluation.",
        url=_cfr("300.502"),
    ),
    LegalProvision(
        id="cfr_300_503",
        short_label="34 C.F.R. § 300.503",
        citation="34 C.F.R. § 300.503",
        kind=AuthorityKind.REGULATION,
        governs="Prior Written Notice (PWN) and its seven required elements",
        agent_use="Check the school's PWNs for compliance, and request PWN "
                  "when services change.",
        url=_cfr("300.503"),
    ),
    LegalProvision(
        id="cfr_300_613",
        short_label="34 C.F.R. § 300.613",
        citation="34 C.F.R. § 300.613",
        kind=AuthorityKind.REGULATION,
        governs="Parent right to inspect and review education records "
                "(without unnecessary delay, before any IEP meeting, and in no "
                "case more than 45 days after the request)",
        agent_use="Legal basis for the service-log request — the parent's right "
                  "to the records that document delivery.",
        url=_cfr("300.613"),
    ),
    LegalProvision(
        id="cfr_300_504",
        short_label="34 C.F.R. § 300.504",
        citation="34 C.F.R. § 300.504",
        kind=AuthorityKind.REGULATION,
        governs="Procedural safeguards notice",
        agent_use="Parent rights reference.",
        url=_cfr("300.504"),
    ),
    LegalProvision(
        id="cfr_300_506",
        short_label="34 C.F.R. § 300.506",
        citation="34 C.F.R. § 300.506",
        kind=AuthorityKind.REGULATION,
        governs="Mediation",
        agent_use="Lower-friction dispute path.",
        url=_cfr("300.506"),
    ),
    LegalProvision(
        id="cfr_300_151_153",
        short_label="34 C.F.R. §§ 300.151–300.153",
        citation="34 C.F.R. §§ 300.151 to 300.153",
        kind=AuthorityKind.REGULATION,
        governs="State complaint procedures",
        agent_use="Default path for service-delivery shortfalls.",
        url=_cfr("300.151"),
    ),
    LegalProvision(
        id="cfr_300_507_516",
        short_label="34 C.F.R. §§ 300.507–300.516",
        citation="34 C.F.R. §§ 300.507 to 300.516",
        kind=AuthorityKind.REGULATION,
        governs="Due process complaint and hearing",
        agent_use="Escalation path for contested cases.",
        url=_cfr("300.507"),
    ),
    # ---- The deadline -------------------------------------------------------
    LegalProvision(
        id="usc_1415_sol",
        short_label="20 U.S.C. § 1415(b)(6), (f)(3)(C)",
        citation="20 U.S.C. § 1415(b)(6), (f)(3)(C)",
        kind=AuthorityKind.STATUTE,
        governs="Two-year statute of limitations for filing",
        agent_use="Drives the deadline clock.",
        url=_usc("1415"),
    ),
    # ---- Case law (verify before reliance) ----------------------------------
    LegalProvision(
        id="endrew_f",
        short_label="Endrew F. v. Douglas County Sch. Dist. RE-1",
        citation="Endrew F. v. Douglas County Sch. Dist. RE-1, 580 U.S. 386 "
                 "(2017)",
        kind=AuthorityKind.CASE,
        governs="Substantive FAPE standard",
        agent_use="Frames whether the program was reasonably calculated to "
                  "enable progress appropriate in light of the child's "
                  "circumstances.",
        url="https://www.oyez.org/cases/2016/15-827",
        verify_required=True,
    ),
    LegalProvision(
        id="van_duyn",
        short_label="Van Duyn v. Baker Sch. Dist.",
        citation="Van Duyn v. Baker Sch. Dist. 5J, 502 F.3d 811 (9th Cir. 2007)",
        kind=AuthorityKind.CASE,
        governs="Material failure to implement standard",
        agent_use="Basis for the materiality threshold rule: a shortfall is "
                  "actionable when the failure to implement is material.",
        url="",
        verify_required=True,
    ),
    LegalProvision(
        id="reid_v_dc",
        short_label="Reid v. District of Columbia",
        citation="Reid ex rel. Reid v. District of Columbia, 401 F.3d 516 "
                 "(D.C. Cir. 2005)",
        kind=AuthorityKind.CASE,
        governs="Compensatory education as a flexible equitable remedy",
        agent_use="Why comp time is an estimated starting position, not a "
                  "mechanical hour-for-hour entitlement.",
        url="",
        verify_required=True,
    ),
    # ---- FERPA (data handling) ---------------------------------------------
    LegalProvision(
        id="ferpa_usc_1232g",
        short_label="20 U.S.C. § 1232g",
        citation="20 U.S.C. § 1232g (FERPA)",
        kind=AuthorityKind.STATUTE,
        governs="Privacy of student education records",
        agent_use="IEPs and service logs are education records; governs the "
                  "data-handling and redaction policy.",
        url=_usc("1232g"),
    ),
    LegalProvision(
        id="cfr_part_99",
        short_label="34 C.F.R. Part 99",
        citation="34 C.F.R. Part 99 (FERPA regulations)",
        kind=AuthorityKind.REGULATION,
        governs="FERPA implementing regulations",
        agent_use="Regulatory basis for the privacy and consent handling.",
        url="https://www.law.cornell.edu/cfr/text/34/part-99",
    ),
]


CORPUS: Dict[str, LegalProvision] = {p.id: p for p in _PROVISIONS}


# --------------------------------------------------------------------------- #
# Lookup / validation helpers
# --------------------------------------------------------------------------- #
def get(provision_id: str) -> LegalProvision:
    """Resolve a provision by id, or raise with the available ids listed."""
    try:
        return CORPUS[provision_id]
    except KeyError:
        raise KeyError(
            f"Unknown legal provision id {provision_id!r}. "
            f"Known ids: {sorted(CORPUS)}"
        ) from None


def exists(provision_id: str) -> bool:
    return provision_id in CORPUS


def validate_refs(provision_ids: List[str]) -> None:
    """Raise if any id is not in the corpus. This is the guard that prevents a
    citation to a legal standard that does not exist in the grounding corpus."""
    unknown = [pid for pid in provision_ids if pid not in CORPUS]
    if unknown:
        raise KeyError(
            f"Citations not in corpus: {unknown}. "
            f"Known ids: {sorted(CORPUS)}"
        )


def cite(provision_id: str) -> str:
    """Short citation string for one provision id."""
    return get(provision_id).cite()


def all_ids() -> List[str]:
    return list(CORPUS)


def by_kind(kind: AuthorityKind) -> List[LegalProvision]:
    return [p for p in CORPUS.values() if p.kind == kind]
