"""Tests for the statute-of-limitations engine."""

from datetime import date

from due_process.deadlines import (
    add_years,
    compute_deadline,
    is_expired,
    is_urgent,
    limitations_years_for,
)


def test_add_years_normal():
    assert add_years(date(2026, 3, 1), 2) == date(2028, 3, 1)


def test_add_years_leap_to_nonleap():
    # Feb 29 + 1yr lands on a non-leap year -> Feb 28.
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)


def test_add_years_leap_to_leap():
    # Feb 29 + 4yr lands on another leap year -> stays Feb 29.
    assert add_years(date(2024, 2, 29), 4) == date(2028, 2, 29)


def test_default_limitations_is_two_years():
    assert limitations_years_for() == 2
    assert limitations_years_for("ZZ") == 2  # unknown state -> federal floor


def test_compute_deadline_two_years():
    clock = compute_deadline("v1", discovery_date=date(2026, 5, 1),
                             today=date(2026, 6, 30))
    assert clock.sol_expiry_date == date(2028, 5, 1)
    assert clock.days_remaining == (date(2028, 5, 1) - date(2026, 6, 30)).days
    assert clock.limitations_years == 2


def test_expired_deadline():
    clock = compute_deadline("v1", discovery_date=date(2020, 1, 1),
                             today=date(2026, 6, 30))
    assert is_expired(clock) is True
    assert clock.days_remaining < 0


def test_urgent_within_threshold():
    clock = compute_deadline("v1", discovery_date=date(2024, 7, 1),
                             today=date(2026, 6, 30))  # expires 2026-07-01
    assert is_urgent(clock) is True
    assert is_expired(clock) is False


def test_explicit_limitations_override():
    clock = compute_deadline("v1", discovery_date=date(2026, 1, 1),
                             today=date(2026, 1, 1), limitations_years=1)
    assert clock.sol_expiry_date == date(2027, 1, 1)
    assert clock.days_remaining == 365
