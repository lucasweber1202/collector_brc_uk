# collector_brc_uk

Standalone collector for the **British Retail Consortium** Shop Price Monitor
(BRC-NIQ Shop Price Index), retrieved through a **licensed delivery provider**.

```
British Retail Consortium          <- the economic publisher
        |
Bloomberg  and/or  LSEG            <- licensed delivery providers
        |
collector_brc_uk                   <- this repository
        |
canonical persisted data contract  <- metadata / time_series / availability /
        |                             source_snapshots / logs
uk_inflation_predictors            <- the research layer
```

BRC remains the publisher. Bloomberg and LSEG are distribution routes the desk is
licensed to use, and they are recorded as provenance, never as the source of the
statistic. Nothing in this repository scrapes a news article, a press release or
a vendor website, and no series is ever reconstructed from the text of a story.

## Current status

`READY_WITH_ENVIRONMENT_GATE`

The architecture, the persistence contract, both provider adapters, the
point-in-time machinery and the offline test suite are complete and pass on a
machine that has never seen a Bloomberg Terminal or an LSEG Workspace. The one
remaining gate is corporate: entitlement, vendor identifier discovery and a live
smoke run. See `VENDOR_INTEGRATION.md` for the exact steps and
[Status vocabulary](#status-vocabulary) for what each term means.

**No live vendor query has been executed.** `LIVE_VENDOR_SMOKE = SKIP`, reason:
no corporate terminal or session available in this environment.

## Canonical series

The identifiers are economic. They do not change when the delivery provider
changes, and a vendor identifier never appears in one.

| `series_id` | Statistic | Unit |
| --- | --- | --- |
| `BRC_SHOP_PRICE_TOTAL_YOY` | Shop Price Index, all shops, year-on-year | percent |
| `BRC_SHOP_PRICE_FOOD_YOY` | Food, year-on-year | percent |
| `BRC_SHOP_PRICE_FRESH_FOOD_YOY` | Fresh food, year-on-year | percent |
| `BRC_SHOP_PRICE_AMBIENT_FOOD_YOY` | Ambient food, year-on-year | percent |
| `BRC_SHOP_PRICE_NONFOOD_YOY` | Non-food, year-on-year | percent |

Six further series (`*_MOM`, `*_INDEX`) are defined in `scripts/series_catalog.py`
as optional. BRC discloses them only in some releases, so they are collected
only once a provider is confirmed to carry a continuous history for them. This
collector never *derives* them from the year-on-year rates: a rate this
repository computed would be a research transformation, not a BRC publication,
and the fleet stores published values only.

## Install and test

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ".[dev]"

pytest -q
ruff check .
ruff format --check .
mypy
python -m compileall -q .
```

All of that passes with no vendor library installed. The vendor libraries are
optional extras, because neither can be installed usefully without an entitled
machine:

```powershell
python -m pip install ".[bloomberg]"   # blpapi, needs a running Terminal
python -m pip install ".[lseg]"        # lseg-data, needs a running Workspace
python -m pip install ".[vendors]"     # both
```

## Run

```powershell
copy .env.example .env      # then set COLLECTOR_DB_URL and DATA_PROVIDER
python main.py
```

Discovery, for the corporate machine:

```powershell
python -m scripts.discover_series --provider bloomberg --query "BRC shop price"
python -m scripts.discover_series --provider bloomberg --fields --query "shop price"
python -m scripts.discover_series --provider lseg --query "BRC shop price"
```

## Provider roles

| Role | Setting | Behaviour |
| --- | --- | --- |
| primary | `DATA_PROVIDER` | Supplies the canonical history. Every stored value comes from here. |
| fallback | `FALLBACK_PROVIDER` | Used **only** when the primary is unreachable. Never on an entitlement failure or an unknown identifier, because both mean the configuration is wrong and failing over would hide that. |
| cross-check | `CROSS_CHECK_PROVIDER` | Read and compared, never written. A disagreement past `CROSS_CHECK_TOLERANCE` fails the run. |

The database never gains a second economic series because the vendor changed.
`BRC_SHOP_PRICE_FOOD_YOY` delivered by LSEG is the same row as delivered by
Bloomberg; only the provenance columns differ.

## Status vocabulary

The earlier fleet status for this source was `blocked_license`, which asserted
that lawful collection was impossible. That is now too coarse. These six facts
are separable, and the status names which of them is still open:

| Term | Meaning | Here |
| --- | --- | --- |
| `SOURCE_EXISTS` | The publisher publishes the statistic. | yes |
| `VENDOR_AVAILABLE` | A licensed delivery provider is available to the desk. | yes — Bloomberg and/or LSEG |
| `ENTITLEMENT_UNKNOWN` | Whether the account may read this data is unverified. | **open** |
| `VENDOR_SERIES_ID_UNKNOWN` | The vendor identifiers are not confirmed. | **open** |
| `IMPLEMENTATION_READY` | Code, schema, tests and PIT handling are complete. | yes |
| `LIVE_CERTIFICATION_PENDING` | No live vendor query has been run. | **open** |

`ready_with_environment_gate` is the repository status when
`IMPLEMENTATION_READY` holds and the only open items are environment-bound.
`pending_vendor_entitlement` would be the status if entitlement were known to be
absent. `implemented_verified` requires a real query against a real provider and
is **not** claimed.

## Licence and safety

BRC data is licensed. This repository therefore contains no BRC values, no
historical fixtures derived from a vendor, no credentials and no vendor
responses. Every test fixture is synthetic and structurally equivalent. Raw
vendor payloads are written to a gitignored `_raw/` directory and never
committed. Redistribution is out of scope: the data is stored for internal
research under the desk's own entitlement.

## Documents

- `METHODOLOGY.md` — what is collected, how it is validated, how the two providers converge.
- `POINT_IN_TIME.md` — the point-in-time contract, and why a vendor backfill is `first_seen`.
- `VENDOR_INTEGRATION.md` — the corporate-machine runbook: entitlement, discovery, smoke.
