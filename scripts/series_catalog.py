"""The canonical BRC series this collector owns.

The identifiers here are economic, not vendor identifiers. A series keeps the
same `series_id` whether Bloomberg or LSEG delivered it, because the publisher
and the statistic are what the identifier describes; the delivery route is
provenance and lives in config/vendor_series.csv and in the vendor columns of
`metadata` and `source_snapshots`.

Only statistics the British Retail Consortium itself publishes appear here. The
BRC-NIQ Shop Price Index headline is a year-on-year rate, and the five
year-on-year rates below are the ones the monthly Shop Price Monitor has
consistently carried. Month-on-month rates, three-month averages and index
levels are listed as OPTIONAL_SERIES: BRC discloses them selectively, and
whether a vendor carries a continuous history for them cannot be established
outside an entitled session. They are collected only once a vendor identifier
for them has actually been confirmed, and never reconstructed by this collector
from the year-on-year rates. A rate this repository computed would be a research
transformation, not a BRC publication, and the fleet stores published levels only.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.config import ORIGINAL_PUBLISHER, PUBLISHER_URL, SOURCE_ID

SURVEY_SHOP_PRICE = "shop_price_monitor"

# The Shop Price Monitor is a published year-on-year rate, not a seasonally
# adjusted index. Nothing in the release describes a seasonal adjustment, so the
# honest value is `not_applicable` rather than a claimed `nsa`.
SEASONAL_ADJUSTMENT = "not_applicable"

REFERENCE_DATE_RULE = (
    "reference_date is the first day of the survey month the rate describes, "
    "normalised from whatever month stamp the delivery provider returns."
)
RELEASE_RULE = (
    "Published monthly, historically about ten days before the ONS CPI release "
    "for the same reference month, at 00:01 Europe/London. The exact instant is "
    "taken from the provider when the provider supplies one and is never assumed."
)
REVISION_POLICY = (
    "BRC publishes no revision policy for the Shop Price Monitor. Restatements "
    "are handled generically: a changed value for a stored reference month "
    "becomes a new vintage and never overwrites the previous one."
)
LICENSE_CONTEXT = (
    "BRC Shop Price Monitor data is licensed. It is obtained here through a "
    "licensed delivery provider (Bloomberg or LSEG) under the desk's own "
    "entitlement, stored for internal research only, and never redistributed."
)


@dataclass(frozen=True)
class SeriesDefinition:
    """One canonical BRC statistic, independent of any delivery provider."""

    series_id: str
    name: str
    description: str
    category: str
    measure: str
    unit: str
    frequency: str
    eco_group: str

    def metadata_fields(self) -> dict[str, object]:
        """Return the catalog half of this series' metadata row."""
        return {
            "source_id": SOURCE_ID,
            "name": self.name,
            "description": self.description,
            "frequency": self.frequency,
            "unit": self.unit,
            "eco_group": self.eco_group,
            "source_url": PUBLISHER_URL,
            "seasonal_adjustment": SEASONAL_ADJUSTMENT,
            "original_publisher": ORIGINAL_PUBLISHER,
            "survey": SURVEY_SHOP_PRICE,
            "measure": self.measure,
            "category": self.category,
            "reference_date_rule": REFERENCE_DATE_RULE,
            "release_rule": RELEASE_RULE,
            "revision_policy": REVISION_POLICY,
            "license_context": LICENSE_CONTEXT,
        }


def _yoy(series_id: str, category: str, label: str, detail: str) -> SeriesDefinition:
    """Build one published year-on-year shop-price rate."""
    return SeriesDefinition(
        series_id=series_id,
        name=f"BRC Shop Price Index, {label}, year-on-year",
        description=(
            f"British Retail Consortium / NIQ Shop Price Index: annual rate of "
            f"change in {detail}, as published in the monthly Shop Price Monitor."
        ),
        category=category,
        measure="yoy",
        unit="percent",
        frequency="monthly",
        eco_group="consumer_prices",
    )


CORE_SERIES: tuple[SeriesDefinition, ...] = (
    _yoy(
        "BRC_SHOP_PRICE_TOTAL_YOY",
        "total",
        "all shops",
        "shop prices across all participating retailers",
    ),
    _yoy(
        "BRC_SHOP_PRICE_FOOD_YOY",
        "food",
        "food",
        "food shop prices",
    ),
    _yoy(
        "BRC_SHOP_PRICE_FRESH_FOOD_YOY",
        "fresh_food",
        "fresh food",
        "fresh food shop prices",
    ),
    _yoy(
        "BRC_SHOP_PRICE_AMBIENT_FOOD_YOY",
        "ambient_food",
        "ambient food",
        "ambient food shop prices",
    ),
    _yoy(
        "BRC_SHOP_PRICE_NONFOOD_YOY",
        "non_food",
        "non-food",
        "non-food shop prices",
    ),
)

# Published by BRC only in some releases. Each becomes collectable the moment a
# vendor identifier for it is confirmed and recorded; until then the registry
# marks it PENDING_VENDOR_DISCOVERY and the run skips it explicitly rather than
# deriving it. Index levels carry unit `index`, month-on-month rates `percent`.
OPTIONAL_SERIES: tuple[SeriesDefinition, ...] = tuple(
    SeriesDefinition(
        series_id=f"BRC_SHOP_PRICE_{suffix}",
        name=f"BRC Shop Price Index, {label}, {measure_label}",
        description=(
            f"British Retail Consortium / NIQ Shop Price Index: {measure_label} for "
            f"{detail}. Published by BRC only in some releases; collected only "
            "when a delivery provider is confirmed to carry a continuous history."
        ),
        category=category,
        measure=measure,
        unit=unit,
        frequency="monthly",
        eco_group="consumer_prices",
    )
    for suffix, category, label, detail, measure, measure_label, unit in (
        (
            "TOTAL_MOM",
            "total",
            "all shops",
            "shop prices across all participating retailers",
            "mom",
            "month-on-month rate",
            "percent",
        ),
        ("FOOD_MOM", "food", "food", "food shop prices", "mom", "month-on-month rate", "percent"),
        (
            "NONFOOD_MOM",
            "non_food",
            "non-food",
            "non-food shop prices",
            "mom",
            "month-on-month rate",
            "percent",
        ),
        (
            "TOTAL_INDEX",
            "total",
            "all shops",
            "shop prices across all participating retailers",
            "index_level",
            "index level",
            "index",
        ),
        ("FOOD_INDEX", "food", "food", "food shop prices", "index_level", "index level", "index"),
        (
            "NONFOOD_INDEX",
            "non_food",
            "non-food",
            "non-food shop prices",
            "index_level",
            "index level",
            "index",
        ),
    )
)

ALL_SERIES: tuple[SeriesDefinition, ...] = CORE_SERIES + OPTIONAL_SERIES
SERIES_BY_ID: dict[str, SeriesDefinition] = {series.series_id: series for series in ALL_SERIES}


def parse_series_id(series_id: str) -> tuple[str, str, str, str]:
    """Decompose a canonical id into (publisher, survey, category, measure).

    Round-trips with the catalog: every id is BRC_SHOP_PRICE_<CATEGORY>_<MEASURE>
    and the parsed parts are the same facts the catalog carries.
    """
    definition = SERIES_BY_ID.get(series_id)
    if definition is None:
        raise KeyError(f"{series_id} is not a canonical BRC series")
    return ("BRC", SURVEY_SHOP_PRICE, definition.category, definition.measure)
