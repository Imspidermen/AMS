"""Campus (application) timezone support.

Storage contract
----------------
Every timestamp column in this application stores a **UTC instant**
(:class:`app.models.entities.UTCDateTime`). This is what keeps instants correct regardless of the
host operating-system timezone and keeps the database portable between SQLite and PostgreSQL.

Business contract
-----------------
Everything a human reads or reasons about — the attendance day, schedule windows, lateness, report
boundaries, exported files, API timestamps and log lines — is expressed in the configured campus
timezone. ``CAMPUS_TIMEZONE`` defaults to ``Asia/Kolkata`` (IST, UTC+05:30), so an attendance record
captured at 2026-10-07 15:00 UTC is displayed, filtered and exported as 2026-10-07 20:30 IST.

Nothing in this module adds a manual ``+5:30`` offset: all conversions use the IANA database through
:mod:`zoneinfo`, which also keeps daylight-saving transitions of other zones correct if a deployment
configures a different campus timezone.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Annotated

from pydantic import AfterValidator
from zoneinfo import ZoneInfo

from app.core.config import settings

UTC = timezone.utc


@lru_cache(maxsize=8)
def _zone(name: str) -> ZoneInfo:
    """Cached IANA lookup; ``ZoneInfo`` construction is cached per name."""
    return ZoneInfo(name)


def campus_timezone_name() -> str:
    """Configured IANA timezone name, e.g. ``Asia/Kolkata``."""
    return settings.campus_timezone


def campus_zone() -> ZoneInfo:
    """Configured campus timezone as an IANA-aware zone object."""
    return _zone(settings.campus_timezone)


def utc_offset_label(value: datetime | None = None) -> str:
    """Offset label such as ``+05:30`` for the campus zone (or for a given instant)."""
    moment = value or utc_now()
    offset = as_utc(moment).astimezone(campus_zone()).utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def utc_now() -> datetime:
    """Current instant as an explicit UTC-aware datetime (storage and internal comparisons)."""
    return datetime.now(UTC)


def campus_now() -> datetime:
    """Current instant expressed in the campus timezone (logging and user-facing output)."""
    return utc_now().astimezone(campus_zone())


def as_utc(value: datetime) -> datetime:
    """Return an instant in UTC; a naive value is read as an already-stored UTC value."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_campus(value: datetime | None) -> datetime | None:
    """Express a stored instant in the campus timezone. ``None`` passes through."""
    if value is None:
        return None
    return as_utc(value).astimezone(campus_zone())


def campus_wall_clock(value: datetime) -> datetime:
    """Return an aware datetime in campus time; a naive value is read as campus wall-clock time."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=campus_zone())
    return value.astimezone(campus_zone())


def campus_to_utc(value: datetime) -> datetime:
    """Interpret an incoming wall-clock value in campus time and return the UTC instant.

    Naive input (for example ``?start=2026-10-07`` or a form field) is treated as campus local time,
    which is what a user in India means by a date. Aware input is converted as-is.
    """
    return campus_wall_clock(value).astimezone(UTC)


def range_start(value: datetime) -> datetime:
    """Lower bound for a campus-local filter: a bare date starts at 00:00 IST."""
    return campus_to_utc(value)


def range_end(value: datetime) -> datetime:
    """Exclusive upper bound for a campus-local filter.

    A bare date means "the whole campus day", so ``end=2026-10-07`` becomes 2026-10-08 00:00 IST and
    a record marked at 23:59 IST is still included. A value carrying a time is used exactly.
    """
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(UTC)
    if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
        return campus_to_utc(value) + timedelta(days=1)
    return campus_to_utc(value)


def campus_date(value: datetime | None) -> date | None:
    """Calendar date (campus timezone) of a stored instant."""
    campus = to_campus(value)
    return None if campus is None else campus.date()


def campus_day_bounds(day: date | datetime) -> tuple[datetime, datetime]:
    """Return the UTC instants bounding a campus calendar day: ``[00:00, next 00:00)``."""
    campus_day = campus_date(day) if isinstance(day, datetime) else day
    assert campus_day is not None
    start = datetime.combine(campus_day, time.min, tzinfo=campus_zone())
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def format_campus(value: datetime | None, pattern: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a stored instant for text output (reports, logs) with an explicit timezone label."""
    campus = to_campus(value)
    return "" if campus is None else campus.strftime(pattern)


# Validators run after pydantic has parsed the ISO-8601 input into a datetime, so a bare date
# (`?start=2026-10-07`) arrives as midnight naive and is then read as campus local wall-clock time.
CampusRangeStart = Annotated[datetime, AfterValidator(range_start)]
"""Filter lower bound: a bare date means 00:00 campus local time."""

CampusRangeEnd = Annotated[datetime, AfterValidator(range_end)]
"""Filter upper bound (exclusive): a bare date means the end of that campus day."""
