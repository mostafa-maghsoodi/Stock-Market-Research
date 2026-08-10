# Measurement and governance review fixes

This revision addresses the four demonstrated defects in the external package review.

## 1. Cross-sectional rank IC

`rank_ic` now requires a panel `DataFrame` containing a decision-date column. It computes Spearman correlation separately inside every date and returns:

- the full per-date IC series;
- mean IC;
- sample standard deviation;
- valid-date count;
- total-date count; and
- the conventional time-series t-statistic when defined.

Flat arrays are rejected. The regression test creates two dates with zero IC inside each date but a pooled correlation above 0.70, and verifies that the reported mean IC remains zero.

## 2. Transaction-cost convention

The only accepted convention is now:

```text
traded_notional = sum(abs(current_weight - prior_weight))
cost = traded_notional * one_way_cost_bps / 10,000
```

The cost rate is read from the verified Entry 001 artifact, not from an independent backtest argument. Initial investment from cash trades 1.0 notional. Complete replacement of one fully invested portfolio with a disjoint portfolio trades 2.0 notional.

## 3. Standalone/Nested/Leave-One-Out diagnostic

The diagnostic now requires four separate score columns:

- candidate standalone;
- base model;
- full model; and
- composite independently recomputed without the candidate.

Nested increment is the paired per-date difference between full and base IC. Ablation increment is the paired per-date difference between full and recomputed leave-one-out IC. The function never aliases leave-one-out to base.

## 4. Entry 001 completeness

Entry 001 now rejects empty:

- `proxy_registry`;
- `research_provenance`;
- `environment_manifest`; and
- `source_control`.

It also requires:

- non-null NumPy and pandas versions;
- exact agreement with the pins in `pyproject.toml`;
- a full Git commit hash;
- a clean working tree; and
- the frozen traded-notional transaction-cost convention and a finite non-negative cost rate.

Regression tests reject each empty artifact independently and reject a simulated NumPy version mismatch.

## Audit-dependent items intentionally not guessed

The market-data path, sector history, investable-universe implementation, dimension-level missing policy, observation periodicity, and return/delisting provenance remain unresolved until the selected vendor data is audited. `README.md` now lists each boundary explicitly.

## Follow-up verification fixes

- Governance test fixtures now use a literal frozen manifest rather than the interpreter running the test. Negative tests therefore cannot pass merely because an unrelated dependency mismatch raised first.
- `environment_manifest()` has a separate runtime-reporting test.
- Entry 001 load compares installed dependency versions with the immutable versions recorded in the frozen artifact. Freeze-time comparison to project pins and load-time comparison to the frozen record are separate operations.
- Core dependency pins are parsed from `pyproject.toml` in a source tree or installed package metadata in a wheel; there is no second hardcoded production copy.
- A zero or negative specification budget is rejected.
- Rank-IC output names the numeric diagnostic `diagnostic_iid_t_stat` and labels its method as an unadjusted IID time-series standard error. The ambiguous `t_stat` field no longer exists.
- ROIC calculates the effective tax rate from reported tax-expense and pretax-income components. The audit rejects `effective_tax_rate` supplied through the fact layer.

## Live API integration

The complete former `Graham.py` service is included as `graham_research.live_app`. Optional FastAPI dependencies and the `graham-live` command keep the live service separate from the analytical runtime. Importing the core package has no live-service side effects, and live outputs remain explicitly barred from historical backtests.

## Pin-authority and freeze-attestation fixes

- Installed distribution metadata is the first pin authority.
- A nearby `pyproject.toml` is only a source-tree fallback, and only when `project.name` normalizes to `graham-systematic-research`; foreign project files are ignored.
- Freeze now validates the actual Python version, implementation, platform, NumPy, and pandas versions against the proposed manifest before writing Entry 001.
- Load repeats the comparison against the immutable versions recorded in Entry 001, without consulting mutable project pins.
- Tests patch a complete deterministic runtime, so negative governance tests cannot pass because of unrelated environmental drift.
- ROIC's Proxy Registry entry now states that tax rates outside `[0, 1]` create non-random missingness associated with loss years, valuation allowances, distress, and cyclical troughs. The dimension-level treatment remains an Entry 001 decision.

The live API remains in the same distribution because integrated delivery was explicitly requested. It is isolated through an optional dependency group, lazy import boundary, live-only response marker, and backtest rejection. Splitting it into a separate repository later would be an architectural deployment choice, not a measurement correction.

## Load-bearing runtime policy

- Installed metadata and a matching source `pyproject.toml` must agree when both are present, preventing stale editable-install metadata from authorizing old pins.
- Exact NumPy and pandas versions are blocking.
- Python implementation and Python major/minor are blocking.
- Python patch and operating-system/platform drift are non-blocking warnings because they remain useful provenance without normally changing the frozen numerical rules.
- Runtime warnings are returned with the loaded Entry 001 and included in every `BacktestResult`.
- Freeze emits the same incidental warnings while still recording the exact original environment inside the hashed artifact.

## Pin-scope and attestation separation

- Project pins are resolved lazily only when creating a manifest or freezing Entry 001. Importing the module and loading a frozen artifact do not consult mutable project pins.
- Stale editable metadata still blocks a new freeze, but cannot block an existing frozen research cycle.
- `require_entry_001` returns `(payload, RuntimeValidationResult)` instead of injecting runtime state into the frozen payload.
- `graham-research check-entry-001` prints non-blocking runtime warnings to stderr and emits the full structured attestation as JSON.
