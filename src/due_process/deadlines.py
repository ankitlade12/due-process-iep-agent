"""The statute-of-limitations clock.

A parent who misses the filing deadline loses the remedy no matter how strong the
case, so the deadline is computed deterministically and surfaced with days
remaining. The federal default is two years from the date the parent knew or
should have known of the violation (20 U.S.C. 1415(b)(6), (f)(3)(C)), unless a
state has an explicit alternative period. Exceptions and state-specific rules
must be reviewed separately, so the configured period is localizable.

``today`` is always passed in explicitly — never read from a hidden clock — so the
math is reproducible and unit-testable.
"""

from __future__ import annotations

from datetime import date

from .models import DeadlineClock

# Federal default. Two years unless a state has an explicit alternative period.
DEFAULT_LIMITATIONS_YEARS = 2

# The two remedies have DIFFERENT clocks — a common, costly trap:
#   * a STATE complaint must allege a violation that occurred not more than ONE
#     year before the complaint is received (34 C.F.R. 300.153(c)); and
#   * a DUE-PROCESS complaint has the TWO-year limitation (20 U.S.C. 1415(b)(6),
#     (f)(3)(C)).
# The state-complaint clock runs from when the violation occurred; the
# due-process clock runs from when the parent knew or should have known.
STATE_COMPLAINT_LOOKBACK_YEARS = 1
DUE_PROCESS_LIMITATIONS_YEARS = 2

# Per-state limitations period in years. The federal default is two years; some
# states adopt a different window or a distinct discovery rule. Populate this map
# only with values verified against the state's special-education regulations —
# an unverified entry is worse than falling back to the federal default. States
# absent from this map use DEFAULT_LIMITATIONS_YEARS.
STATE_LIMITATIONS_YEARS: dict[str, int] = {
    # "TX": 1,   # example shape only — verify before enabling
}

# Surface a deadline as urgent when fewer than this many days remain.
URGENT_THRESHOLD_DAYS = 90


def limitations_years_for(state: str = "") -> int:
    """The configured period, using the two-year federal default when unknown."""
    return STATE_LIMITATIONS_YEARS.get(state.upper(), DEFAULT_LIMITATIONS_YEARS)


def add_years(d: date, years: int) -> date:
    """Add whole years to a date, handling the Feb 29 edge.

    Feb 29 plus a non-leap number of years lands on Feb 28, the conventional
    treatment when the anniversary day does not exist.
    """
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Only Feb 29 -> non-leap year reaches here.
        return d.replace(year=d.year + years, day=28)


def compute_deadline(
    violation_id: str,
    discovery_date: date,
    today: date,
    *,
    state: str = "",
    limitations_years: int | None = None,
) -> DeadlineClock:
    """Compute the SoL clock for a violation.

    Args:
        violation_id: the violation this clock is for.
        discovery_date: when the parent knew or should have known.
        today: the reference date for ``days_remaining``.
        state: two-letter state code, used to localize the period.
        limitations_years: explicit override of the period in years.
    """
    years = (
        limitations_years
        if limitations_years is not None
        else limitations_years_for(state)
    )
    expiry = add_years(discovery_date, years)
    days_remaining = (expiry - today).days
    return DeadlineClock(
        violation_id=violation_id,
        discovery_date=discovery_date,
        sol_expiry_date=expiry,
        days_remaining=days_remaining,
        state=state,
        limitations_years=years,
    )


def state_complaint_deadline(
    violation_id: str,
    violation_date: date,
    today: date,
    *,
    state: str = "",
) -> DeadlineClock:
    """The deadline to include a violation in a STATE complaint.

    One year from the date the violation occurred (34 C.F.R. 300.153(c)). Pass the
    earliest violation date to know when the oldest events age out of eligibility.
    """
    expiry = add_years(violation_date, STATE_COMPLAINT_LOOKBACK_YEARS)
    return DeadlineClock(
        violation_id=violation_id, discovery_date=violation_date,
        sol_expiry_date=expiry, days_remaining=(expiry - today).days,
        state=state, limitations_years=STATE_COMPLAINT_LOOKBACK_YEARS,
        remedy="state_complaint", basis="cfr_300_153",
    )


def due_process_deadline(
    violation_id: str,
    discovery_date: date,
    today: date,
    *,
    state: str = "",
) -> DeadlineClock:
    """The deadline to file a DUE-PROCESS complaint.

    Two years by federal default from when the parent knew or should have known
    (20 U.S.C. 1415(b)(6), (f)(3)(C)); a state may set a different period and
    statutory exceptions require separate review.
    """
    years = limitations_years_for(state)
    expiry = add_years(discovery_date, years)
    return DeadlineClock(
        violation_id=violation_id, discovery_date=discovery_date,
        sol_expiry_date=expiry, days_remaining=(expiry - today).days,
        state=state, limitations_years=years,
        remedy="due_process", basis="usc_1415_sol",
    )


def is_expired(clock: DeadlineClock) -> bool:
    return clock.days_remaining < 0


def is_urgent(clock: DeadlineClock,
              threshold_days: int = URGENT_THRESHOLD_DAYS) -> bool:
    """True when the deadline is near (or past) and warrants prompt action."""
    return clock.days_remaining < threshold_days
