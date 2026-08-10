# Graham Systematic Research — Python MVP

This package implements the first safe coding boundary of **Architecture v3.1**. It does not claim that any signal predicts returns, and it does not generate buy/sell recommendations.

## What this code implements

- Versioned, point-in-time fact observations keyed to actual public availability timestamps.
- Explicit `first_reported` and `latest_known` restatement policies.
- Structural data auditing with the architecture's eight required fields.
- A proposed Proxy Registry and deterministic MVP calculations for:
  - Valuation: FCF/EV and EBIT/EV.
  - Business Economics: gross profitability and ROIC.
  - Fundamental Change: operating-margin change, FCF-margin change, and revenue acceleration.
- Cross-sectional percentile ranks with deterministic tie and missing-data behavior.
- Equal-weight feature, dimension, and final composite construction.
- Per-decision-date cross-sectional Spearman rank IC with its per-date series, mean, standard deviation, valid-date count, and conventional time-series t-statistic.
- A four-vector Standalone/Base/Nested/Leave-One-Out diagnostic. Leave-one-out must be a separately recomputed composite and is never aliased to the base model.
- Exact Rule #17 calculation using `numpy.percentile(..., method="linear")`.
- Immutable Entry 000/001 files with SHA-256 verification. Entry 001 rejects empty proxy, provenance, environment, and source-control artifacts and rejects environments that differ from the pinned analytical dependencies.
- An append-only specification log.
- A small equal-weight portfolio test engine that refuses to run without a valid, complete Entry 001 freeze. Costs use one frozen convention: `sum(abs(delta_weight)) * one_way_cost_bps`, so initial deployment trades 1.0 notional and a complete portfolio replacement trades 2.0.
- The complete former `Graham.py` FastAPI service as the optional `graham_research.live_app` module, with SEC analysis, warnings, thesis storage, reviews, closures, scorecards, and thesis diffs.
- A lazy `graham-live` launcher and a hard boundary marking every live response as ineligible for historical backtesting.

## What remains intentionally unresolved

Architecture v3.1 deliberately makes these audit or governance decisions rather than programming defaults:

- Data vendor and vendor-vintage schema.
- Survivorship-complete security master and delisting returns.
- Exact investable-universe thresholds.
- Which candidate proxy definitions survive the audit and enter the frozen cycle.
- Development, Holdout A, and Holdout B dates.
- Estimates-data admissibility.
- Statistical decision procedure and multiplicity treatment.
- Rebalance frequency, holding period, and the one-way transaction-cost rate.

The following measurement paths remain blocked on the vendor audit and must not be invented in advance:

- Decision-date market prices and enterprise value, including a frozen staleness bound.
- Daily adjusted-price history and 12-1 momentum.
- Point-in-time sector classifications and sector-routing behavior.
- A survivorship-complete L1 investable-universe module.
- Dimension-level missing-data policy.
- Annual/quarterly periodicity metadata and gap checks for change features.
- Return provenance, delisting inclusion, and alignment to the frozen holding period.

The file `examples/entry001.template.json` makes every unresolved decision visible. The CLI refuses to freeze that template until all placeholders are replaced.

## Integrated live analysis

The former standalone `Graham.py` is now packaged at `src/graham_research/live_app.py`. The original file in Downloads is no longer required to run the integrated project.

Install the optional live dependencies:

```bash
python -m pip install -e '.[live]'
```

Set the required configuration and start it:

```bash
export SEC_USER_AGENT='YourAppName/1.0 your-email@example.com'
export GRAHAM_API_KEY='choose-a-long-random-password'
export GRAHAM_DB_PATH='./graham_theses.db'
graham-live
```

The default host is `127.0.0.1` and the default port is `8000`. Override them with `GRAHAM_LIVE_HOST` and `GRAHAM_LIVE_PORT`. For local testing only, authentication can be disabled with `GRAHAM_REQUIRE_AUTH=0`.

The primary endpoints remain:

- `GET /analyze/{ticker}`
- `GET /thesis/scorecard`
- `GET /thesis`
- `POST /thesis`
- `GET /thesis/{thesis_id}`
- `POST /thesis/{thesis_id}/review`
- `POST /thesis/{thesis_id}/close`
- `GET /thesis/{thesis_id}/diff`

Every analysis response now includes:

```json
{
  "research_eligibility": {
    "scope": "live_analysis_only",
    "historical_backtest_eligible": false
  }
}
```

Do not use its annual arrays directly in a backtest. Current SEC Company Facts can contain later amendments and comparative values from later filings, and the live API lacks a historical security master, delisted names, delisting returns, and historically adjusted prices. `graham_research.legacy.assess_graham_snapshot` enforces this boundary.

## Expected input shape

Fundamental data uses one row per source version:

```text
security_id,field,period_end,available_at,value,source,accession,unit
```

`available_at` must be timezone-aware and must represent when that exact version became public. Period type, reporting frequency, form type, fiscal year, and fiscal quarter are explicit source metadata; absent values remain `unknown`/null and are never inferred. See `examples/facts.example.csv`.

## Install and run

Use Python 3.11 or later:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Audit a fact panel before calculating features:

```bash
graham-research audit-facts examples/facts.example.csv audit.json
```

Freeze the architecture before the audit:

```bash
graham-research freeze-entry-000 /path/to/architecture-v3.1.txt research/entry000.json
graham-research verify research/entry000.json
```

After the audit and every governance choice are complete, copy and resolve the Entry 001 template, then freeze it:

```bash
graham-research manifest --repository /path/to/clean/git/repository > research/manifests.json
graham-research freeze-entry-001 research/entry001.config.json research/entry001.json --repository /path/to/clean/git/repository
graham-research verify research/entry001.json
graham-research check-entry-001 research/entry001.json
```

The manifest command records exact Python, platform, NumPy, and pandas versions and a full Git commit. When installed metadata and a matching source `pyproject.toml` both exist, their pins must agree; this detects stale editable installs. A nearby `pyproject.toml` belonging to another project is never accepted.

Entry 001 compares the real interpreter with the manifest during both freeze and load. Exact NumPy/pandas versions, Python implementation, and Python major/minor are blocking. Python patch and platform changes remain recorded but produce warnings rather than vetoing the research cycle.

`require_entry_001(path)` returns `(frozen_payload, runtime_validation)`, keeping the hashed artifact structurally separate from current-machine observations. The `check-entry-001` CLI command prints non-blocking warnings to stderr and returns the structured attestation as JSON. Backtests copy the warnings into `BacktestResult.runtime_warnings`.

Project-pin discovery is lazy and is only used by manifest/freeze operations. Importing governance code, loading an existing Entry 001, running a backtest, or evaluating Rule #17 does not consult current project pins or stale editable-install metadata.

Evaluate Rule #17:

```bash
graham-research rule17 0.11 0.12 0.10 0.14 0.13
```

Run tests without additional test dependencies:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Minimal library example

```python
from datetime import datetime

from graham_research.domain import FactObservation
from graham_research.features import FeatureEngine
from graham_research.governance import load_resolved_entry_001
from graham_research.pit import PointInTimeStore

facts = [FactObservation.from_mapping(row) for row in vendor_rows]
store = PointInTimeStore(facts)
decision_at = datetime.fromisoformat("2025-03-31T20:00:00+00:00")
resolved = load_resolved_entry_001("research/entry001.json")
engine = FeatureEngine(store, resolved)
features = engine.calculate_governed_batch(
    ["SECURITY-123"], decision_at, repository="/path/to/clean/repository"
)
```

Governed feature construction requires a verified Entry 001 v2 and a clean
source tree. Unresolved specifications fail at the freeze gate and cannot reach
ranking. Market-derived role alignment remains explicitly unresolved in Run 1;
frequency exemption does not solve historical market-data timing.

The next production step is a vendor-specific adapter that preserves the `FactObservation` contract. It should be written only after the data-source audit establishes which timestamps, revisions, delistings, and classifications are genuinely point-in-time.
