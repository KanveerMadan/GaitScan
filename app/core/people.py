"""Who GaitScan measures: adults only, with an optional sex for the cadence reference (2026-11-12)."""

from datetime import date
from typing import Literal

ADULT_AGE = 18
OLDEST_BIRTH_YEAR = 1900
# Only what the published reference reports (Mobbs et al. 2025: females and males); optional everywhere.
Sex = Literal["female", "male"]


def adult_birth_years() -> tuple[int, int]:
    """The birth years of someone 18 or over today, oldest first."""
    return OLDEST_BIRTH_YEAR, date.today().year - ADULT_AGE


def adult_birth_year_error() -> str:
    lo, hi = adult_birth_years()
    return f"GaitScan is for adults (18 or over): a birth year from {lo} to {hi}."
