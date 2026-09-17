# Vendor integration runbook — collector_brc_uk

Everything in this repository that can be built outside the corporate
environment is built. What remains needs an entitled machine. This is that list.

## Environment actions required at Kinea

1. Open the **Bloomberg Terminal** and log in on the machine that will run the
   collector. The Desktop API answers on `localhost:8194` only while the
   Terminal session is live.
2. `python -m pip install ".[bloomberg]"`.
3. Run discovery:
   ```powershell
   python -m scripts.discover_series --provider bloomberg --query "BRC shop price"
   python -m scripts.discover_series --provider bloomberg --query "British Retail Consortium"
   python -m scripts.discover_series --provider bloomberg --fields --query "shop price"
   ```
4. Confirm entitlement and identity for the five BRC indicators: for each
   candidate, check that the description is the BRC statistic, that its history
   starts where BRC's does, and that the field returns the published rate.
5. Write the confirmed `identifier`, `field`, `vendor_description`,
   `history_start` and `confirmed_on` into `config/vendor_series.csv`. Nothing
   else changes — no parser, no schema, no database work.
6. Run the vendor smoke: `python -m scripts.vendor_smoke --provider bloomberg`.
7. Repeat steps 1–6 for **CBI** in `collector_cbi_uk`.

If LSEG is available, the same flow with **LSEG Workspace** running,
`python -m pip install ".[lseg]"`, and `--provider lseg`. A desk on a platform
session instead configures `lseg-data.config.json` and points
`LD_LIB_CONFIG_PATH` at it; that file is gitignored and holds the app key.

## Why the identifiers are not already here

Bloomberg tickers, Bloomberg field mnemonics, LSEG RICs, vendor series ids and
entitlements cannot be confirmed outside an entitled session. Every unconfirmed
cell in `config/vendor_series.csv` therefore holds the literal sentinel
`PENDING_VENDOR_DISCOVERY`, and `tests/test_registry_and_architecture.py` fails
if any shipped row carries anything else.

This is not caution for its own sake. A plausible-looking invented ticker has
two outcomes: it fails loudly, wasting a day, or it resolves to a *different*
statistic and silently poisons the stored history with numbers that look right.
The second outcome is unrecoverable without noticing it first.

The loader also refuses an identifier recorded without a `confirmed_on` date, so
"someone pasted a ticker" and "someone verified a ticker" stay distinguishable.

## What discovery actually calls

Both providers support programmatic search, so the discovery command is a real
tool and not a placeholder:

- **Bloomberg** — `//blp/instruments` (`instrumentListRequest`) returns
  securities matching a free-text query with their descriptions.
  `//blp/apiflds` (`FieldSearchRequest`) returns field mnemonics matching a
  description. Together they answer both halves of a registry row.
- **LSEG** — `lseg.data.discovery.search` returns matching instruments with
  their RICs and descriptions.

Discovery deliberately **does not write** to `config/vendor_series.csv`. A
search result is a candidate, not a confirmation; an automatic write would turn
"the search returned something" into "the ticker is correct". The command prints
the candidates and the exact CSV cells to fill, so the manual step is a review
rather than a transcription.

If a search returns nothing for every wording, that is a finding to record — not
a reason to fall back to a guess.

## Failure states you should expect to see

Each produces a distinct, auditable exception rather than an empty result:

| Situation | Exception |
| --- | --- |
| Library not installed, Terminal/Workspace not running | `ProviderUnavailableError` |
| Session rejected | `VendorAuthenticationError` |
| Valid session, no entitlement | `EntitlementError` |
| Unknown ticker or RIC | `IdentifierNotFoundError` |
| Unknown field | `FieldNotFoundError` |
| Valid, entitled, zero rows | `EmptyHistoryError` |
| Timeout, throttle, restart | `TemporaryProviderError` |
| Series still unmapped | `PendingVendorDiscoveryError` |

Only `ProviderUnavailableError` and `TemporaryProviderError` trigger the
fallback provider. An entitlement failure or an unknown identifier means the
configuration is wrong, and failing over would hide that.

## Live smoke

`python -m scripts.vendor_smoke --provider <bloomberg|lseg>` performs, in order:
authenticate, fetch one series, fetch a small window, validate the canonical
schema, report the latest value, persist, rerun, and confirm the rerun wrote
nothing.

**Current result: `LIVE_VENDOR_SMOKE = SKIP`, reason: no corporate terminal or
session available.** It is not marked `PASS`, and it must not be until it has
actually run. Only then does the repository move from
`ready_with_environment_gate` to `implemented_verified`, in this README and in
`uk_inflation_predictors/collector_registry.csv`.
