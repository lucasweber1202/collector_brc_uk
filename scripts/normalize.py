"""The canonical contract every delivery provider must converge on.

Bloomberg and LSEG return different objects for the same BRC statistic. This
module defines the one shape they are both normalised into, so the rest of the
collector never learns which provider it is reading, and so that
`BRC_SHOP_PRICE_FOOD_YOY` means exactly the same stored series whichever route
delivered it. The database never gains a second economic series because the
vendor changed.

Two normalisations matter enough to be done here rather than in either adapter:

* Reference month. Providers stamp a monthly observation with the first day,
  the last day, or a datetime inside the month. All three mean the same survey
  month, so all three collapse to the first of that month. Anything finer than
  a month is rejected rather than truncated, because a weekly or daily stamp
  from a monthly series means the identifier is wrong.
* Publication instants. BRC publishes in London, which is GMT for part of the
  year and BST for the rest. A naive vendor timestamp is therefore interpreted
  in Europe/London through the tz database and converted to UTC, never through
  a fixed offset, which would be wrong for half the year.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from scripts.config import PUBLICATION_TIMEZONE
from scripts.series_catalog import SERIES_BY_ID
from scripts.time_series import Observation
from scripts.vendor_errors import EmptyHistoryError

LONDON = ZoneInfo(PUBLICATION_TIMEZONE)


@dataclass(frozen=True)
class VendorRow:
    """One observation exactly as a delivery provider reported it."""

    reference_date: date
    value: float | None
    release_timestamp: datetime | None = None


@dataclass(frozen=True)
class VendorSeriesResponse:
    """One provider's answer for one canonical series.

    `query` is the full, ordered description of what was asked. It is part of
    the snapshot digest, so a history retrieved over a different window or field
    can never be mistaken for the same artifact.
    """

    provider: str
    series_id: str
    identifier: str
    field: str
    query: dict[str, str]
    rows: tuple[VendorRow, ...]
    retrieved_at: datetime
    vendor_description: str = ""
    warnings: tuple[str, ...] = ()


def to_utc(moment: datetime) -> datetime:
    """Return `moment` in UTC, reading a naive instant as Europe/London.

    GMT and BST are both resolved from the tz database by the date itself. A
    fixed offset would silently shift every summer publication by an hour.
    """
    localised = moment.replace(tzinfo=LONDON) if moment.tzinfo is None else moment
    return localised.astimezone(UTC)


def london_midnight_utc(day: date) -> datetime:
    """Return 00:01 Europe/London on `day`, expressed in UTC.

    The Shop Price Monitor has historically been released one minute after
    midnight London time. This is used only where a release *date* is known
    without a time; it is never used to invent a release that was not reported.
    """
    return to_utc(datetime.combine(day, time(hour=0, minute=1), tzinfo=LONDON))


def normalise_reference_date(value: date | datetime | str) -> date:
    """Collapse a provider's month stamp onto the first day of that month."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise TypeError(f"Cannot read {value!r} as a reference date")
    return value.replace(day=1)


def _is_month_stamp(value: date) -> bool:
    """True when a date is a plausible monthly stamp: a month's first or last day."""
    if value.day == 1:
        return True
    next_month = date(value.year + value.month // 12, value.month % 12 + 1, 1)
    return value.day == (next_month - date.resolution).day


def canonical_observations(response: VendorSeriesResponse, snapshot_id: str) -> list[Observation]:
    """Validate one provider response and turn it into canonical observations.

    Every rejection here is a loud failure rather than a dropped row. A monthly
    BRC series that arrives with mid-month stamps, duplicate months or no rows
    at all is evidence that the identifier or the field is wrong, and quietly
    keeping the rows that happen to parse would store a plausible, wrong history.
    """
    if response.series_id not in SERIES_BY_ID:
        raise ValueError(f"{response.series_id} is not a canonical BRC series")
    usable = [row for row in response.rows if row.value is not None and math.isfinite(row.value)]
    if not usable:
        raise EmptyHistoryError(
            response.provider,
            f"{response.series_id} ({response.identifier}/{response.field}) returned "
            f"{len(response.rows)} rows and no usable value. An empty history is never "
            "treated as a successful collection.",
        )
    observations: list[Observation] = []
    seen: dict[date, float] = {}
    for row in usable:
        if not _is_month_stamp(row.reference_date):
            raise ValueError(
                f"{response.series_id}: {response.provider} returned {row.reference_date} for a "
                "monthly series. A stamp that is neither the first nor the last day of a month "
                "means the requested identifier is not the monthly BRC series."
            )
        reference_date = normalise_reference_date(row.reference_date)
        value = float(row.value)  # type: ignore[arg-type]
        if reference_date in seen:
            if seen[reference_date] != value:
                raise ValueError(
                    f"{response.series_id}: {response.provider} returned two different values "
                    f"for {reference_date} ({seen[reference_date]} and {value})."
                )
            continue
        seen[reference_date] = value
        observations.append(
            Observation(
                series_id=response.series_id,
                reference_date=reference_date,
                value=value,
                snapshot_id=snapshot_id,
            )
        )
    observations.sort(key=lambda observation: observation.reference_date)
    return observations


def release_instants(response: VendorSeriesResponse) -> dict[date, datetime]:
    """Return the provider-supplied publication instant per reference month.

    Only genuinely reported timestamps appear. A month with no reported instant
    is absent from the mapping, and the caller stamps it `first_seen` rather
    than reconstructing a release time it was never told.
    """
    instants: dict[date, datetime] = {}
    for row in response.rows:
        if row.release_timestamp is None:
            continue
        instants[normalise_reference_date(row.reference_date)] = to_utc(row.release_timestamp)
    return instants


def compare_responses(
    primary: VendorSeriesResponse, other: VendorSeriesResponse, tolerance: float
) -> list[str]:
    """Report where a cross-check provider disagrees with the primary.

    Returns human-readable differences rather than raising: a cross-check is
    evidence for the run log and for an operator, not a reason to discard the
    primary's value. The canonical history has exactly one source of truth per
    run, and silently preferring whichever provider happened to answer would
    make the stored series depend on provider availability.
    """
    if primary.series_id != other.series_id:
        raise ValueError("Cross-check compares one canonical series at a time")
    left = {normalise_reference_date(r.reference_date): r.value for r in primary.rows}
    right = {normalise_reference_date(r.reference_date): r.value for r in other.rows}
    differences: list[str] = []
    for reference_date in sorted(set(left) & set(right)):
        a, b = left[reference_date], right[reference_date]
        if a is None or b is None:
            continue
        if abs(a - b) > tolerance:
            differences.append(
                f"{primary.series_id} {reference_date}: {primary.provider}={a} "
                f"{other.provider}={b} (tolerance {tolerance})"
            )
    only_primary = sorted(set(left) - set(right))
    only_other = sorted(set(right) - set(left))
    if only_primary:
        differences.append(
            f"{primary.series_id}: {len(only_primary)} months only in {primary.provider} "
            f"(first {only_primary[0]}, last {only_primary[-1]})"
        )
    if only_other:
        differences.append(
            f"{primary.series_id}: {len(only_other)} months only in {other.provider} "
            f"(first {only_other[0]}, last {only_other[-1]})"
        )
    return differences


def snapshot_payload(response: VendorSeriesResponse) -> dict[str, Any]:
    """Return the deterministic description of a response for hashing.

    `retrieved_at` is deliberately excluded. It changes on every run, and
    including it would make every rerun produce a new snapshot digest, which
    would destroy the idempotency the snapshot table exists to provide. The
    retrieval instant is still recorded, in the snapshot row's `fetched_at`
    column, where it is evidence rather than identity.
    """
    return {
        "provider": response.provider,
        "series_id": response.series_id,
        "identifier": response.identifier,
        "field": response.field,
        "query": {key: response.query[key] for key in sorted(response.query)},
        "rows": [
            {
                "reference_date": row.reference_date.isoformat(),
                "value": row.value,
                "release_timestamp": (
                    to_utc(row.release_timestamp).isoformat()
                    if row.release_timestamp is not None
                    else None
                ),
            }
            for row in sorted(response.rows, key=lambda row: row.reference_date)
        ],
    }
