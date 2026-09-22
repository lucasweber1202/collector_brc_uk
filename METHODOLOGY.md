# Methodology — collector_brc_uk

This repository belongs to the UK inflation predictor fleet. It collects raw
explanatory variables (X) only. Forecast targets (Y), CPI weights and bottom-up
reconciliation remain owned by `collector_ons_cpi` / `collector_ons_ex_cpi`.

## Publisher and delivery provider

The **British Retail Consortium**, with NIQ, compiles and publishes the Shop
Price Index. That is the economic fact this collector stores.

**Bloomberg** and **LSEG** are licensed delivery providers. They are how the
desk lawfully obtains the series; they are not its author. The distinction is
enforced in code, not only in prose: `vendor_provenance.original_publisher` must name
BRC, and `scripts/metadata.py` rejects a row that names a delivery provider
there. Provider identity lives in `vendor_provenance.delivery_provider`,
`vendor_provenance.vendor_series_id`, `vendor_provenance.vendor_field` and in the vendor columns
of `source_snapshots`.

This is why there is no `collector_bloomberg_uk` and no `collector_reuters_uk`.
A collector is named for a publisher. A vendor is a route, and routes are
recorded per observation rather than given a repository.

## What is collected

Five published year-on-year Shop Price Monitor rates: all shops, food, fresh
food, ambient food and non-food. Six further series (month-on-month rates and
index levels) are defined and are collectable the moment a provider is confirmed
to carry a continuous history for them.

Nothing is derived. If BRC does not publish a month-on-month rate and no vendor
delivers one, this collector does not compute one from the year-on-year series.
A computed rate is a research transformation and belongs in
`uk_inflation_predictors`, alongside the lags and the MoM/YoY features the
research layer builds for every predictor.

## Database tables

`metadata`, `time_series`, `availability`, `source_snapshots`, `logs`, `vendor_provenance` — the
five base fleet tables plus one source-specific table, in a schema named `collector_brc_uk`.

Two documented deviations, both forced by the delivery model rather than chosen:

1. `vendor_provenance` carries vendor provenance and survey dimensions
   (`original_publisher`, `delivery_provider`, `vendor_series_id`,
   `vendor_field`, `vendor_description`, `survey`, `measure`, `category`,
   `seasonal_adjustment`, `reference_date_rule`, `release_rule`,
   `revision_policy`, `license_context`, `history_start`), plus its source-specific
   `source_id`.
2. `source_snapshots` carries `delivery_provider`, `vendor_series_id`,
   `vendor_field`, `vendor_query` and `vendor_row_count`, because `source_url`
   cannot identify an API response.

Together these let any stored observation be traced back to: *this BRC
statistic, delivered by this provider, under this identifier and field, over
this query window, retrieved at this instant, first knowable at this instant on
this basis, from a response with this digest.*

## Snapshots without bytes

A public-file collector hashes the file it downloaded. There is no file here: a
licensed provider answers with objects over an API. The snapshot identity is
therefore the SHA-256 of a canonical, deterministic serialization of the request
and the rows it returned — sorted keys, sorted rows, stable separators.

The retrieval instant is deliberately **excluded** from the digest. Including it
would give every rerun a new snapshot id, so the run that should have written
nothing would write a fresh snapshot row for every series every day, and the
table would stop being evidence of change. The instant is still recorded, as
`source_snapshots.fetched_at`, where it is evidence rather than identity.

## Validation before persistence

Every provider response is validated in `scripts/normalize.py` before anything
is written, and each failure is loud rather than a dropped row:

- **Empty history is an error, never an empty success.** This is the failure
  mode a vendor-delivered collector must not ship. An entitlement failure, an
  unknown identifier and a genuinely empty window all look like "no rows" unless
  they are separated, and a collector that shrugs at no rows silently stops
  tracking a series forever. `scripts/vendor_errors.py` gives each state its own
  exception.
- **Month stamps.** Providers stamp a monthly observation at the month's first
  day, its last day, or a datetime inside it; all three collapse to the first.
  Anything finer than a month is *rejected*, not truncated: a mid-month stamp on
  a monthly series means the requested identifier is not the BRC series.
- **Duplicates.** The same month twice with the same value collapses. With two
  different values, the run fails.
- **Canonical ids.** Only ids in `scripts/series_catalog.py` can be stored.

## Two providers, one series

Both adapters converge on `VendorSeriesResponse`, and `tests/test_normalize.py`
asserts that a Bloomberg response and an LSEG response carrying the same history
produce byte-identical canonical observations — including when one uses
month-end stamps and the other month-start.

Roles are strict. The **primary** supplies every stored value. The **fallback**
is used only when the primary is *unreachable*; an entitlement failure or an
unknown identifier is never failed over, because both mean the configuration is
wrong and switching vendors would hide that behind plausible data. The
**cross-check** is read and compared but never written, and a material
disagreement fails the run: two licensed routes to one BRC statistic returning
different numbers means one of the two identifiers is wrong.

## Idempotency and revisions

An unchanged rerun writes no `time_series`, `availability` or `source_snapshots`
rows and leaves `metadata` untouched; only the run log changes. A later-day
change to a stored month inserts a new vintage and preserves the old one. A
same-day change fails closed, because the fleet key stores `vintage_date` as a
DATE and cannot represent two intraday information sets without rewriting
history. All three runs are asserted in `tests/test_persistence.py`.

## Timezone

BRC publishes in London. Naive vendor timestamps are interpreted in
`Europe/London` through the tz database and converted to UTC, so GMT and BST are
both handled by the date itself. A fixed offset would be wrong for half the
year, and is never used.

## Isolation

No module imports another collector, `uk_inflation_predictors`, or a shared
package. There is no `BaseCollector`, no vendor framework, no `core/` and no
subpackage under `scripts/`. `tests/test_registry_and_architecture.py` parses
every file in the repository and fails if any of that appears.
