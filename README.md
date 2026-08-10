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
- Source-owned governed fact and held-return datasets loaded only from an immutable, locally audited ingest manifest plus its bound content hash.
- Content-bound ranking artifacts whose digest and selector authority cover exactly `security_id`, `decision_date`, and `composite_score`.
- An append-only OPEN/CLOSE/blocked specification register with pre-execution classification and atomic research-budget reservation.
- A governed equal-weight portfolio engine with exact schedule-derived holding intervals, an independent held-return source, continuous drift, and turnover from drifted pre-rebalance weights.
- The complete former `Graham.py` FastAPI service as the optional `graham_research.live_app` module, with SEC analysis, warnings, thesis storage, reviews, closures, scorecards, and thesis diffs.
- A lazy `graham-live` launcher and a hard boundary marking every live response as ineligible for historical backtesting.

## What remains intentionally unresolved

Architecture v3.1 deliberately makes these audit or governance decisions rather than programming defaults:

- Production data vendor and vendor-backed manifest/signature integration. The MVP verifies an audited local ingest artifact and does not claim vendor attestation.
- Survivorship-complete security master and delisting returns.
- Exact investable-universe thresholds.
- Which candidate proxy definitions survive the audit and enter the frozen cycle.
- Development, Holdout A, and Holdout B dates and each boundary's inclusion, overlap, gap, and shared-boundary semantics.
- Estimates-data admissibility.
- Statistical decision procedure and multiplicity treatment.
- Rebalance schedule, holding period, schedule anchor and anchor meaning, portfolio size, insufficient-name behavior, and the one-way transaction-cost rate.
- Governed research-vintage bundle identity. Fact-source and return-source native vintage identifiers remain independent source observations.
- Terminal disposition/proceeds timing, terminal turnover/cost/redeployment, terminal continuation across skipped rebalances, cash returns, and post-OPEN slot release.

The following measurement paths remain blocked and must not be invented in advance:

- Decision-date market prices and enterprise value, including a frozen staleness bound.
- Daily adjusted-price history and 12-1 momentum.
- Point-in-time sector classifications and sector-routing behavior.
- A survivorship-complete L1 investable-universe module.
- Dimension-level missing-data policy.
- Annual/quarterly periodicity metadata and gap checks for change features.
- Executable terminal/delisting accounting. The current closed executable policy is `fail_on_any_terminal_event`; even an observed terminal total return is not enough to define proceeds state, disposition timing, turnover, transaction costs, and redeployment.
- `hold_cash`, because no governed cash-return source exists.
- Holding periods unequal to rebalance intervals, because overlapping holding lots or an intervening cash state would require additional frozen portfolio-state rules.

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

Call live analysis with an explicitly supplied current price:

```bash
curl -H "X-API-Key: $GRAHAM_API_KEY" \
  'http://127.0.0.1:8000/analyze/AAPL?price=200.00'
```

Current/live SEC analysis is not eligible for historical backtesting.

## Expected input shape

Fundamental data uses one row per source version:

```text
security_id,field,period_end,available_at,value,source,accession,unit
```

`available_at` must be timezone-aware and must represent when that exact version became public. Period type, reporting frequency, form type, fiscal year, and fiscal quarter are explicit source metadata; absent values remain `unknown`/null and are never inferred. See `examples/facts.example.csv`.

Governed loading additionally requires a frozen source-manifest JSON and its
`.sha256` sidecar. The exact MVP manifest fields are:

```text
source_manifest_schema_version
source_kind                         # pit_facts or held_period_returns
source_id
research_vintage_bundle_id          # must equal Entry 001
source_native_vintage_identifier    # independent for each source
content_sha256
audit_artifact_sha256
provenance                          # audited_local_ingest_manifest
economic_return_convention          # held_period_returns only; exact timing match
```

The loader verifies the immutable manifest identity and the bound content
bytes. This is an audited local-ingest mechanism, not a vendor-signed claim.
No feature, ranking, preflight, or backtest API accepts a vintage string as a
runtime override.

Held-return manifests use source-manifest schema version 2 and additionally
bind an exact economic return convention. Entry 001 separately freezes the
decision-information cutoff, executable portfolio timing, return-measurement
start and end, official-session basis, IANA market timezone, endpoint inclusion,
and held-return definition. Governed preflight requires exact equality between
those fields and the independently audited return source. Schedule dates remain
interval labels; date equality alone never asserts economic equivalence.

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

After the audit has informed Architecture v3 and the researcher has approved it,
freeze Entry 000 explicitly:

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

Evaluate Rule #17 as an ungoverned mathematical diagnostic helper:

```bash
graham-research rule17 0.11 0.12 0.10 0.14 0.13
```

Run tests without additional test dependencies:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Governed historical research workflow

The required order is:

1. Obtain legitimate historical PIT accounting data and map every source version into `FactObservation`.
2. Run `audit-facts` and inspect its period/fiscal-year metadata coverage.
3. Resolve frequency, source-field, period-structure, denominator, missingness, timing, boundary, construction, terminal, budget, and research-vintage governance; update Architecture v3.
4. Explicitly freeze and verify Entry 000, then Entry 001 v2. The software never performs either freeze automatically.
5. Load the fact CSV through its immutable audited local-ingest manifest; compute clean-tree governed date batches and combine them.
6. Rank and create a clean-tree governed ranking artifact. The ranking commit must equal the feature-generation commit.
7. Freeze the ranking package and inspect its manifest plus bound canonical decision frame.
8. Load an independent held-period return source through its own immutable manifest. Its research-vintage bundle must match Entry 001; its source-native vintage need not match the fact source's.
9. Call the governed backtest entry point with a predeclared `run_class`, rationale, sample partition, and specification register.
10. The engine completes deterministic preflight, atomically checks the budget and appends OPEN, then—and only then—uses a forward return to compute gross return and drift. It appends CLOSE afterward.
11. Inspect the register and remaining budget.

Preparation and governance commands:

```bash
graham-research audit-facts /path/to/pit-facts.csv audit.json
python -m json.tool audit.json | less

graham-research freeze-entry-000 /path/to/architecture-v3.1.txt research/entry000.json
graham-research verify research/entry000.json

cp examples/entry001.template.json research/entry001.config.json
# Resolve every placeholder and update Architecture v3 before continuing.
graham-research manifest --repository "$PWD" > research/current-manifests.json
graham-research freeze-entry-001 research/entry001.config.json research/entry001.json --repository "$PWD"
graham-research verify research/entry001.json
graham-research check-entry-001 research/entry001.json

graham-research inspect-ranked-artifact research/ranking.manifest.json
graham-research spec-budget research/entry001.json --repository "$PWD"
graham-research spec-log --repository "$PWD"
```

There is intentionally no detached `spec-open` or `run-strategy` command. OPEN
is issued only by the integrated governed execution path after complete
deterministic preflight; a standalone command could reserve a slot without
proving the prepared inputs.

## Minimal governed library outline

```python
from datetime import datetime

from graham_research.backtest import run_equal_weight_backtest
from graham_research.datasets import (
    load_governed_fact_dataset,
    load_governed_held_return_source,
)
from graham_research.features import FeatureEngine, combine_governed_feature_batches
from graham_research.governance import load_resolved_entry_001
from graham_research.ranked_artifact import (
    create_governed_ranking_artifact,
    write_ranking_manifest,
)
from graham_research.specification import (
    RunClass, RunType, SpecificationRegister, SpecificationRequest,
)

resolved = load_resolved_entry_001("research/entry001.json")
facts = load_governed_fact_dataset(
    "research/pit-facts.csv", "research/pit-facts.manifest.json"
)
engine = FeatureEngine(facts, resolved)
date_batches = [
    engine.calculate_governed_batch(
        security_ids,
        datetime.fromisoformat(value),
        repository="/path/to/clean/repository",
    )
    for value in governed_decision_timestamps
]
features = combine_governed_feature_batches(
    date_batches, repository="/path/to/clean/repository"
)
ranking = create_governed_ranking_artifact(
    features, resolved, repository="/path/to/clean/repository"
)
write_ranking_manifest(ranking, "research/ranking.manifest.json")

held_returns = load_governed_held_return_source(
    "research/held-returns.csv", "research/held-returns.manifest.json"
)
register = SpecificationRegister.for_repository("/path/to/clean/repository")
result = run_equal_weight_backtest(
    ranking,
    held_returns,
    "research/entry001.json",
    "/path/to/clean/repository",
    register,
    SpecificationRequest(
        run_class=RunClass.RESEARCH_SPECIFICATION,
        rationale="pre-registered primary development-sample test",
        run_type=RunType.PORTFOLIO_BACKTEST,
    ),
    sample_partition="development",
)
```

Unresolved specifications fail the Entry 001 freeze gate and cannot reach
governed ranking/composite or outcome execution. Composite collapse from
unavailable unresolved proxies is diagnostic/counterfactual only, never a
bypass around the freeze gate.

The selector tie-break is an inherited Run 1 software invariant:
`composite_score` descending, then `security_id` ascending. It is exposed in
the ranking-configuration digest and bound again by the clean Git commit. The
ranked-frame content digest attests only to `security_id`, `decision_date`, and
`composite_score`; it does not attest to auxiliary feature, dimension,
coverage, exclusion, or diagnostic columns, and the governed selector cannot
read those columns.

Preflight may read a return solely to establish schema, coverage, uniqueness,
and finiteness, and it returns no outcome-bearing statistic. The first
result-producing use is
`backtest._produce_portfolio_results_after_open()`, called only through
`execution.execute_opened_experiment()` with an internal execution authorization.
The authorization is issued only after the register rereads and strictly
validates its entire history, proves that the OPEN is unique and unclosed, and
matches its immutable event digest, prepared-experiment digest, lineage,
parameters, run class, and run type. The prepared digest binds Entry 001, both
source identities and content hashes, ranked-frame scope/content, ranking and
proxy configuration, all three code commits, sample/portfolio/timing/cost
parameters, schedule and holding-interval keys, selected and held IDs, and
structural return keys. It contains no return values; the audited return-source
content hash binds those values. Result lineage is copied from the verified OPEN,
not reconstructed from mutable preparation state. Public IC, triad, and Rule 17
functions remain ungoverned mathematical helpers and cannot emit governed
result artifacts.

`SpecificationRegister.for_repository(repository, path=...)` is the only
write-authorized register construction. An explicit path may be outside the
repository or inside it only when Git confirms it is ignored. The generic
constructor is read-only, and no public generic OPEN method exists. Portfolio
outcomes are limited to `research_specification`; diagnostic and data-correction
portfolio requests stop before OPEN. Data-correction linkage is checked against
register history, but outcome execution remains disabled because this MVP has no
approved specification-invalidation mechanism.

With `partition_gap_policy=allow`, a gap date belongs to no sample partition and
cannot be scheduled for an OPEN. It is never assigned by inference from ranked
data.

Every research-specification OPEN counts as budget used. If execution fails or
is abandoned after OPEN, OPEN remains immutable and a failed/abandoned CLOSE is
appended. Whether such a slot may ever be released is unresolved; no release
mechanism exists, so the interim accounting cannot silently create budget.

Market-derived role alignment remains explicitly unresolved. Current
valuation/EV features are not historically economically PIT-complete until a
separately audited historical market-data layer binds decision-date price or
market capitalization to accounting values known at that same decision date.
Frequency exemption does not solve this blocker.

The next production step is a vendor-specific adapter that preserves the `FactObservation` contract. It should be written only after the data-source audit establishes which timestamps, revisions, delistings, and classifications are genuinely point-in-time.
