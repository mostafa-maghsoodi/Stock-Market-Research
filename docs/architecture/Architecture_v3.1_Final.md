# Architecture v3.1

## Systematic, Explainable Stock-Selection Research Framework

**Status:** Architecture closed
**Stage:** Pre-return research design
**Purpose:** Define a falsifiable, point-in-time, explainable research system for long-term individual-stock selection before examining strategy-return results.

---

## 1. Objective

The objective is to build:

> **The smallest explainable set of economically distinct signals that demonstrates robust, out-of-sample incremental information about future stock returns after realistic implementation costs.**

The system is a research and ranking framework.

It is not:

* an automated “AI tells me what to buy” system;
* a claim that future returns can be predicted with certainty;
* a collection of factors assembled because they performed well historically;
* a general technical-analysis engine;
* or a justification for complexity.

Every candidate feature must answer three questions:

1. **What information does it measure?**
2. **Why might that information not already be fully reflected in price?**
3. **What empirical result would cause us to reject it?**

Complexity receives no presumption of value.

A feature, module, or model survives only by producing evidence consistent with its economic hypothesis under the frozen research protocol.

---

# 2. Governing Information Model

The architecture separates company and market information into economically distinct objects.

## 2.1 Accounting Level

What is true about the business now?

Examples:

* profitability;
* assets;
* liabilities;
* cash generation;
* reinvestment;
* leverage;
* margins;
* working capital;
* capital employed.

---

## 2.2 Accounting Change

How is realized business performance changing?

Examples:

* margin improvement or deterioration;
* FCF improvement;
* revenue acceleration;
* earnings improvement;
* changing capital efficiency.

---

## 2.3 Expectations Level

What does the current valuation or market price appear to require?

Examples:

* earnings yield;
* FCF yield;
* enterprise-value-based valuation;
* implied growth;
* implied margins;
* reverse-DCF assumptions.

---

## 2.4 Expectations Change

How are expectations changing?

Examples:

* analyst revision breadth;
* revision magnitude;
* estimate dispersion;
* changing consensus forecasts.

---

## 2.5 Market Change

How is the equity market itself updating?

Primary initial example:

* 12-1 price momentum.

Price is therefore not treated as a mysterious independent information source.

The **price level** enters valuation.

The **change in price** enters Market Change.

---

## 2.6 Positioning and Constraints

Are different investors, markets, or participants processing the same company differently?

Examples may eventually include:

* credit markets;
* insider behavior;
* short interest;
* ownership structure;
* forced selling;
* liquidity constraints;
* options markets.

---

# 3. Edge Hypothesis Registry

Every return-seeking module must map to an explicit economic mechanism.

## H1 — Overreaction

**Mechanism:** Markets may push viable businesses below reasonable fundamental value after adverse periods.

Possible manifestations:

* extreme valuation;
* stabilization following deterioration;
* excessive pessimism relative to normalized business economics.

---

## H2 — Underreaction

**Mechanism:** New information may enter prices gradually because investors update slowly, anchor to prior expectations, or face institutional frictions.

Possible manifestations:

* improving fundamentals;
* analyst revisions;
* earnings revisions;
* price momentum.

---

## H3 — Capital-Allocation Mismeasurement

**Mechanism:** Persistent management behavior involving financing, reinvestment, M&A, buybacks, issuance, or leverage may be underweighted or incorrectly interpreted.

Possible manifestations:

* net issuance;
* acquisition outcomes;
* buybacks net of stock-based compensation;
* incremental returns on invested capital;
* impairment history.

---

## H4 — Information Segmentation

**Mechanism:** Equity investors, credit investors, analysts, insiders, and constrained holders may observe or respond to information at different speeds.

Possible manifestations:

* credit-spread changes;
* analyst revisions;
* insider activity;
* short-interest changes;
* ownership/positioning changes.

---

## H5 — Persistence Mispricing — Provisional

**Mechanism:** Markets may over-apply mean reversion to businesses with unusually durable profitability or business economics.

Possible manifestations:

* persistent ROIC;
* gross profitability;
* margin stability;
* durable cash conversion.

H5 exists only provisionally.

Business Economics must demonstrate independent empirical relevance or be demoted or removed.

No hypothesis receives inherited empirical credibility merely because it is famous, academically documented, Graham-inspired, or commonly used.

---

# 4. System Architecture

The research system contains ten layers.

## L0 — Point-in-Time Data

Historical information exactly as it was available at each historical date.

## L1 — Investable Universe

Investability and true data-sufficiency restrictions only.

## L2 — Feature Library

Deterministic raw measurements.

## L3 — Information Dimensions

Economically distinct candidate information sources.

## L4 — Identification and Redundancy Control

Tests whether apparent independent information is genuinely distinct.

## L5 — Decision / Composite Layer

Simple combination of surviving information.

## L6 — Deep Valuation / Expectations

Reverse DCF and detailed expectations work for finalists.

## L7 — LLM Evidence Layer

Structured evidence extraction from filings and disclosures.

## L8 — Portfolio Construction and Exits

Sizing, constraints, turnover, costs, entry and exit rules.

## L9 — Monitoring

Live signal behavior, drift, decay, failed hypotheses, and specification history.

---

# 5. L0 — Point-in-Time Data

Data engineering is module zero.

A valid backtest requires data that reproduces what could actually have been known at the historical decision date.

Required design includes:

* fundamentals keyed to actual public availability dates;
* filing or announcement dates;
* first-reported versus restated values separated;
* delisted securities retained;
* delisting returns included;
* point-in-time shares outstanding;
* historically appropriate adjusted prices;
* historical listing status;
* historical sector and industry classifications;
* point-in-time analyst estimates where used;
* historical ownership or credit information where used;
* source provenance for material fields.

## Data-quality principle

> **Data-quality standards do not relax when historical coverage disappoints.**

If usable point-in-time history begins later than expected:

1. shorten the sample;
2. revise Development / Holdout A / Holdout B boundaries;
3. document the loss of statistical power.

Do not lower the point-in-time standard simply to preserve sample length.

---

# 6. L1 — Investable Universe

Only genuine investability and data-sufficiency restrictions belong here.

Possible categories include:

* eligible exchanges;
* listing type;
* security type;
* liquidity;
* ADV;
* minimum price where operationally justified;
* minimum trading history;
* minimum accounting history;
* sector-specific routing;
* legitimate security exclusions.

Fundamental cheapness, profitability, Graham ratios, momentum, or similar economic characteristics should not become early hard filters merely because they were historically used in screens.

The rejected architecture is:

> Graham → Quality → GARP → Valuation → AI → Decision.

The reason for rejecting it is structural:

> Early fundamental filters can permanently remove companies before other economically independent dimensions evaluate them.

The exact investable-universe specification is a frozen artifact in Entry 001.

---

# 7. L2 — Feature Library

Features are deterministic measurements, not investment conclusions.

For every feature, the Proxy Registry records:

* exact formula;
* source fields;
* availability lag;
* expected direction;
* transformation;
* winsorization or truncation if any;
* sector treatment;
* missing-data treatment;
* known accounting weaknesses;
* economic interpretation.

Cross-sectional ranks are preferred where raw values are fat-tailed or unstable.

Sector-relative measurements are used only when economically justified.

---

# 8. L3 — Information Dimensions

## 8.1 Valuation

**Primary hypothesis:** H1.

Purpose:

> Measure the amount of economic output obtained relative to the current price or enterprise value.

Candidate representations may include:

* FCF / EV;
* EBIT / EV;
* earnings yield;
* GP / EV where economically defensible;
* a deliberately simple rank composite.

Valuation ratios and reverse DCF are conceptually related but not identical.

Simple valuation ratios are cross-sectional measurements.

Reverse DCF is a model-based inference about expectations and remains primarily in L6.

---

## 8.2 Business Economics

**Primary hypothesis:** H5, provisional.

Purpose:

> Measure the underlying strength, profitability, persistence, accounting quality, and capital efficiency of the business.

Candidate representations may include:

* ROIC;
* ROIC stability;
* gross profitability / assets;
* cash conversion;
* accrual quality;
* margin stability;
* financial strength;
* ordinary leverage and coverage measures.

Business Economics is not automatically an independent alpha factor.

It may ultimately become:

* an independent signal;
* a valuation conditioner;
* a risk variable;
* or nothing.

Its survival is empirical.

---

## 8.3 Capital Allocation

**Primary hypothesis:** H3.

Capital Allocation separates two questions.

### Allocation Skill

Did management deploy capital in ways that subsequently improved business economics?

### Allocation Discipline

Did management choose rational uses of capital given valuation, leverage, and available alternatives?

Candidate measures include:

* net issuance;
* actual share-count change;
* buybacks net of stock-based compensation;
* external financing;
* asset growth;
* incremental NOPAT / incremental invested capital;
* acquisition spending versus subsequent operating improvement;
* impairment history;
* leverage behavior across cycles;
* issuance behavior relative to valuation.

A manager may allocate capital poorly and yet that behavior may already be fully reflected in price.

Therefore Capital Allocation must establish not merely that management behavior matters operationally, but that the measured behavior contains forward return information beyond other known constructs.

---

## 8.4 Fundamental Change

**Primary hypothesis:** H2.

This dimension contains realized accounting change.

Examples:

* margin trajectory;
* FCF improvement or deterioration;
* revenue acceleration;
* operating profitability change;
* earnings improvement;
* selected Piotroski-style changes.

Analyst revisions do not belong here.

---

## 8.5 Expectations Change

**Primary hypotheses:** H2 and potentially H4.

Candidate measures include:

* revision breadth;
* revision magnitude;
* dispersion change;
* point-in-time consensus change.

This dimension exists historically only if the data audit establishes a defensible point-in-time estimate dataset.

If historical estimates are materially backfilled, restated, or cannot reproduce contemporaneously available information, Expectations Change is excluded from the research cycle.

The audit determines admissibility before any forward-return test.

---

## 8.6 Market Change

**Primary hypotheses:** H1 and H2.

Primary initial signal:

> **12-1 momentum**

The research question is not:

> Does momentum work historically?

The research question is:

> Does adding a simple market-change signal improve the otherwise identical fundamental system out of sample after realistic costs?

Possible later candidates may include:

* distance from the 52-week high.

No broad technical-indicator module is included initially.

---

## 8.7 Fragility

Fragility is narrowly defined as:

> **Nonlinear survival, financing, or permanent-impairment risk.**

It is not simply “low Quality.”

Potential measurements include:

* maturity concentration;
* refinancing dependence;
* covenant headroom;
* acute liquidity runway;
* severe dilution dependence;
* going-concern conditions;
* distress probability;
* existential customer concentration.

Ordinary leverage and coverage ratios generally belong in Business Economics unless they are explicitly being used to model nonlinear distress risk.

Fragility may ultimately function as:

* a continuous signal;
* a sizing input;
* a nonlinear conditioner;
* a threshold;
* or nothing.

Its functional form is an empirical question.

---

## 8.8 Positioning / Constraints

**Primary hypothesis:** H4.

This is a later research track rather than part of the first MVP.

Possible future information includes:

* credit-spread changes;
* short-interest changes;
* insider clusters;
* ownership changes;
* options-market information.

These signals are attractive because they may represent genuinely different information sources, but they also create greater vendor dependency, shorter histories, and more implementation complexity.

---

# 9. Excluded or Postponed Technical Analysis

The initial system does not include a general technical-analysis module.

Postponed or excluded initially:

* RSI;
* MACD;
* Bollinger Bands;
* moving-average crossovers;
* support/resistance;
* Fibonacci retracements;
* large technical-indicator libraries;
* short-term reversal.

The reason is not a blanket assertion that technical analysis cannot contain information.

The reason is that many of these indicators are deterministic transformations of:

* returns;
* trend;
* volatility.

They therefore introduce additional researcher degrees of freedom before demonstrating genuinely distinct information.

## Fibonacci

Fibonacci is particularly low priority because performance can depend heavily on:

* swing selection;
* lookback windows;
* retracement levels;
* tolerance rules;
* signal life;
* confirmation rules;
* failure rules;
* holding periods.

If Fibonacci is ever revisited, the pre-specified falsification experiment is:

> Compare canonical Fibonacci retracement levels against arbitrary placebo retracement levels under the identical algorithm.

If arbitrary levels perform similarly, no special Fibonacci effect has been established.

---

# 10. L4 — Identification and Redundancy Control

The purpose of L4 is not merely to calculate correlations.

It asks:

> Have we actually identified an independent information source?

Required diagnostics include:

* Spearman rank correlation;
* standalone rank IC;
* conditional IC;
* nested incremental tests;
* leave-one-out ablation;
* factor regression;
* control-definition robustness;
* sector stability;
* subperiod stability;
* residualization only when economically interpretable;
* PCA only as a diagnostic.

Do not automatically sum correlated scores.

Do not automatically residualize them.

Residualization is order-dependent and therefore embeds an economic judgment about which variable is primary and which is a control.

---

# 11. Standalone / Nested / Leave-One-Out Triad

Every important dimension must be viewed three ways.

## Standalone

Does the dimension contain information by itself?

## Nested

What happens when the dimension is added at its planned place in the model?

## Leave-One-Out

What happens when the dimension is removed from the otherwise complete simple model?

The nested ladder is useful as a reporting and engineering device.

It is not allowed to allocate causal credit merely because one variable entered first.

If standalone, nested, and ablation results disagree, the disagreement is treated as diagnostic evidence about overlap.

It is not resolved by selecting whichever result is most favorable.

---

# 12. Feature Failure and Construct Failure

These are separate concepts.

## Feature Failure

A particular implementation fails.

Example:

> One ROIC formula fails.

This does not automatically falsify Business Economics.

---

## Construct Failure

Every frozen admissible representation of the construct fails the pre-specified testing framework.

Example:

> All frozen Business Economics proxies fail.

Then the construct and its associated hypothesis fail for that research cycle.

No new representation may be invented after observing the failure.

A genuinely new proxy requires a new research cycle.

---

# 13. Proxy Registry

Before forward-return testing begins, each major construct receives a fixed, written set of exact representations.

A specification budget is not a substitute for this enumeration.

For every proxy, record:

* construct;
* exact formula;
* data source;
* source fields;
* availability lag;
* sign;
* transformation;
* sector treatment;
* missing-data treatment;
* known accounting weakness;
* rationale.

Business Economics and Valuation should be enumerated first because they are expected to serve as the most important control constructs.

No weak proxy is invented merely to increase the proxy count.

---

# 14. Rule #17 — Control-Definition Robustness

Rule #17 governs claims that a candidate contains information **independent of another latent construct**.

For candidate signal (S), calculate its sign-aligned incremental effect under every frozen admissible representation of control construct (C):

[
\Delta_1,\Delta_2,\ldots,\Delta_k
]

The control-definition robustness test applies only when:

[
k \ge 5
]

Compute the 25th and 75th percentiles using exactly:

```
numpy.percentile(delta_values, [25, 75], method="linear")

```

The NumPy version is frozen in the environment manifest.

Define:

[
Q_{25}=P_{25}(\Delta)
]

[
Q_{75}=P_{75}(\Delta)
]

and:

[
IQR=Q_{75}-Q_{25}
]

The criterion passes only when:

[
Q_{25}>0
]

and:

[
Q_{25}>IQR
]

For positive quantiles, this is equivalent to:

[
\frac{Q_{75}}{Q_{25}}<2
]

## If (k<5)

Independence from that control construct is **not established for the research cycle**.

This does not invalidate:

* standalone IC;
* monotonicity;
* portfolio contribution;
* other direct evidence for the candidate.

It only blocks the stronger claim that the candidate is independent of the inadequately represented control construct.

A weakly identified incremental relationship cannot, by itself, serve as the load-bearing statistical evidence for a Holdout A pass.

## Interpretation

Rule #17 measures:

> **robustness to control measurement.**

It does not measure:

* statistical significance;
* economic magnitude;
* portfolio harvestability.

Those are tested separately.

---

# 15. L5 — Decision / Composite Layer

The initial decision model should be intentionally simple.

Preferred starting design:

* cross-sectional ranks;
* simple normalization;
* equal or similarly transparent weighting;
* very few hard vetoes;
* deterministic treatment of missing values.

Avoid initially:

* fitted weights;
* neural networks;
* gradient boosting;
* large interaction grids;
* dynamic regimes;
* flexible threshold optimization;
* complex ML ranking.

The composite itself is not the edge.

The surviving information is.

---

# 16. L6 — Deep Valuation / Expectations

Deep valuation applies only to finalists.

Possible process:

1. reverse DCF;
2. infer price-implied revenue growth;
3. infer price-implied margins;
4. infer required reinvestment assumptions;
5. compare with company history;
6. compare with peer and historical base rates;
7. construct Bear / Base / Bull cases;
8. assess margin of safety.

The purpose is not false precision.

The purpose is to understand:

> **What operating future must occur for the current market price to make sense?**

A good company is not automatically a good investment at the current price.

---

# 17. L7 — LLM Evidence Layer

Governing rule:

> **LLM extracts evidence; code calculates numbers.**

Appropriate tasks include:

* comparing risk-factor language year over year;
* identifying added or removed risk disclosures;
* customer concentration;
* auditor changes;
* going-concern language;
* related-party transactions;
* segment disclosure changes;
* non-GAAP drift;
* acquisition rationale;
* management promises versus later disclosed results.

Preferred output is structured evidence:

* finding;
* filing;
* filing date;
* source span;
* current disclosure;
* prior disclosure;
* change;
* economic relevance;
* confidence.

The LLM should not generate opaque numerical investment scores.

---

## 17.1 Measurement Validation

Can the LLM accurately extract the intended evidence?

Methods may include:

* labeled human samples;
* precision/recall;
* human adjudication;
* test-retest reliability;
* prompt-paraphrase robustness;
* source-span verification.

---

## 17.2 Economic Validation

Does the extracted evidence contain incremental forward information?

Historical LLM backtesting receives lower evidentiary weight because pretrained models may contain later knowledge about historical companies.

Research breadth and production breadth should be decoupled.

The LLM may extract evidence across a large random research sample even if only a much smaller number of stocks ever become portfolio finalists.

Prospective validation receives greater evidentiary weight than historically contaminated prediction-style tests.

---

# 18. L8 — Portfolio Construction and Exits

Portfolio construction is part of the research specification.

It must not be deferred until after signal discovery.

Eventually define:

* number of holdings;
* equal weight versus other sizing;
* position caps;
* sector caps;
* liquidity caps;
* ADV limits;
* turnover budget;
* rebalance frequency;
* holding-period convention;
* transaction costs;
* slippage;
* tax assumptions where relevant;
* concentration/correlation controls;
* entry rules;
* exit rules;
* delisting treatment;
* merger treatment.

Primary rebalance frequency and primary holding-period convention are frozen before return testing.

Any permitted robustness alternatives are enumerated before results.

---

# 19. L9 — Monitoring

Live monitoring records:

* live versus backtest IC;
* signal decay;
* portfolio turnover;
* realized costs;
* factor exposures;
* drawdowns;
* longest benchmark-relative underperformance;
* specification drift;
* failed hypotheses;
* deviations from preregistration.

Failed experiments remain visible.

They are not silently removed from the research history.

---

# 20. Research Governance

A numeric specification budget is frozen before strategy-return testing.

The budget governs allowed experiments using the frozen representations.

It does not permit invention of new representations after failures.

A distinct specification includes deliberate changes capable of affecting the investment result, including:

* feature definitions;
* accounting normalization;
* lag conventions;
* transformations;
* winsorization;
* control sets;
* weights;
* thresholds;
* windows;
* universe rules;
* holding periods;
* rebalance frequency;
* implementation assumptions used to make research decisions.

Confirmed coding or data corrections are treated separately but remain logged.

A correction cannot be relabeled after the fact merely because the original result was unfavorable.

The exact numeric budget is unresolved at Entry 000 and must be frozen in Entry 001 before any strategy-return test.

---

# 21. Governance Choices vs Audit-Determined Outcomes

Between Entry 000 and Entry 001, unresolved items fall into two categories.

## Governance Choices

These are settled ex ante using economic and operational judgment.

Examples:

* numeric specification budget;
* rebalance frequency;
* holding period;
* operational universe rules such as liquidity floors where multiple defensible choices exist.

---

## Audit-Determined Outcomes

These are not optimization variables.

The data audit decides them.

Examples:

* actual usable PIT start date;
* estimate-data admissibility;
* sector-history availability;
* feasible Proxy Registry representations;
* Development / Holdout A / Holdout B boundaries implied by usable coverage.

The governing rule is:

> **Audit-determined decisions follow data validity first and statistical convenience second.**

A smaller-than-desired sample does not justify changing the historical-data standard.

---

# 22. Holdout Design

The project preserves two chronological reserves.

## Development Sample

Used for:

* development;
* diagnostics;
* permitted research specifications.

## Holdout A

First untouched evaluation sample.

## Holdout B

Second untouched chronological reserve.

Exact boundaries are determined from the PIT data audit before return testing.

The boundaries are based on valid coverage, not on performance.

Shorter historical coverage does not justify collapsing Holdout B into Development.

Once both chronological reserves have been consumed, genuinely new temporal evidence must increasingly come from live forward performance.

---

# 23. Holdout A Pass

“Passes Holdout A” must be numerically operationalized before Holdout A is opened.

The Entry 001 package must specify:

* primary signal metric;
* primary portfolio metric;
* statistical decision procedure;
* alpha/error rate;
* multiplicity correction;
* dependence treatment;
* resampling or permutation procedure;
* transaction-cost methodology.

A successful Holdout A result requires both:

## Statistical Requirement

The frozen full model clears the pre-specified primary statistical decision rule.

## Economic Implementation Requirement

The frozen primary portfolio metric remains positive after the frozen transaction-cost model.

A statistically detectable but economically unharvestable signal does not constitute a successful system.

---

# 24. Falsification Hierarchy

## Feature-Level Failure

A specific implementation fails.

Action:

> Drop the implementation.

---

## Construct-Level Failure

All frozen admissible representations of the construct fail.

Action:

> Reject the construct and associated edge hypothesis for the research cycle.

---

## System-Level Failure

All pre-registered edge hypotheses fail their construct-level requirements.

Action:

> Reject the stock-selection alpha system for the research cycle.

Failure does not authorize unplanned feature invention using the same holdout.

New hypotheses require a new research cycle and explicitly weaker or genuinely new evidence.

---

# 25. Benchmark Framework

The initial nested reporting ladder is:

[
M0 = \text{Equal-weight investable universe}
]

[
M1 = \text{Value}
]

[
M2 = \text{Value + Business Economics}
]

[
M3 = \text{M2 + Fundamental Change}
]

[
M4 = \text{M3 + Expectations Change}
]

if Expectations Change is PIT-admissible.

[
M5 = \text{M4 + 12-1 Momentum}
]

The ladder is a reporting device.

It does not assign causal ownership of overlapping information.

Every major dimension is also evaluated through:

* standalone tests;
* leave-one-out ablation.

Additional benchmarks include:

* broad index;
* equal-weight investable universe;
* simple one-factor value model;
* simple value + quality model;
* known factor models;
* matched random portfolios.

The complex system must demonstrate why it deserves to exist relative to substantially simpler alternatives.

---

# 26. MVP

The architecture is deliberately broader than the first empirical model.

The initial MVP should remain small.

## Initial Core

> **Value + Business Economics + Fundamental Change**

If the estimates audit supports a defensible PIT vintage:

> **+ Expectations Change**

Then test:

> **+ 12-1 Momentum**

Capital Allocation follows after clean measurement is defined.

Postponed until later:

* Positioning / Constraints;
* full-universe reverse DCF;
* complex LLM-derived research signals;
* elaborate capital-allocation taxonomies;
* technical-indicator libraries;
* ML ranking;
* optimized weights.

---

# 27. Data Audit Protocol

Negative audit findings receive the most detailed documentation because they change the boundary of what the research can validly claim.

Every adverse finding receives eight fields.

## 1. Finding

What exactly failed?

## 2. Evidence

What schema, documentation, timestamps, sample inspection, or other evidence establishes the problem?

## 3. Contamination Mechanism

What bias would arise if the field were nevertheless used?

## 4. Affected Construct / Test

Which proxy, dimension, normalization, or validation step depends on the field?

## 5. Eligibility Decision

Classify it as:

* admissible;
* admissible only after a specified date;
* admissible subject to a frozen restriction;
* excluded.

## 6. Sample Impact

How does the decision affect:

* Development;
* Holdout A;
* Holdout B;
* universe breadth?

## 7. Power / Coverage Cost

What statistical or cross-sectional information is lost?

## 8. No-Workaround Statement

Does any legitimate engineering solution preserve the same point-in-time standard?

This final field distinguishes:

> engineering around a constraint

from

> quietly redefining the constraint.

Examples:

If historical consensus estimates are materially backfilled and no genuine contemporaneous vintage exists, Expectations Change is excluded.

If historical sector classifications are reconstructed using later classifications, sector-relative analysis begins only when genuine as-of sector information exists unless another valid source is obtained.

Bad audit news is not a research obstacle.

It is a research result about the experiment that can validly be performed.

---

# 28. Graham Screener Treatment

The existing Graham screener receives zero inherited empirical credit.

Every rule is mapped through four provenance categories.

## Metric Provenance

Why is the variable present?

Possible sources:

* Graham;
* academic literature;
* practitioner literature;
* personal reasoning;
* later adaptation.

## Functional-Form Provenance

Why is the metric expressed as:

* ratio;
* rank;
* binary rule;
* threshold;
* composite?

## Threshold Provenance

Where did the cutoff originate?

Was it:

* inherited;
* economically derived;
* chosen before seeing data;
* modified after seeing data?

## Sample Exposure

What historical evidence may already have influenced the inclusion of the rule?

For many classical Graham rules, the appropriate statement may simply be:

> **Inherited from a widely studied historical rule; therefore heavily exposed to prior sample evidence.**

Age, fame, and survival in investment literature confer no empirical credit inside Architecture v3.1.

The Graham mapping asks:

> What economic construct is this rule attempting to measure?

Then classify each existing rule as:

* investability rule;
* continuous feature;
* conditioner;
* diagnostic;
* possible true gate;
* redundant measurement;
* deletion candidate.

The mapping describes the old screener.

It does not validate it.

---

# 29. Entry 000 — Architecture Preregistration

Entry 000 is created and hashed **before the data audit**.

Its purpose is to establish that the architecture and methodology existed before strategy-return evidence was examined.

Entry 000 contains:

* Architecture v3.1;
* Edge Hypothesis Registry;
* Rule #17;
* falsification hierarchy;
* research-governance principles;
* audit protocol;
* explicit statement that no strategy-return results were examined in designing Architecture v3.1;
* unresolved operational items.

The unresolved list should explicitly include, where applicable:

* data-audit findings;
* exact investable-universe values;
* Proxy Registry formulas;
* estimate-data admissibility;
* Development / Holdout A / Holdout B dates;
* numeric specification budget;
* transaction-cost parameters;
* rebalance frequency;
* holding period;
* exact statistical implementation details not yet audit-resolved.

Entry 000 is not rewritten later to make the research record look cleaner.

---

# 30. Entry 001 — Full Experimental Freeze

Entry 001 is created after the data audit and Proxy Registry are complete but before the first strategy-return test.

It is the complete experimental freeze.

The hashed Entry 001 package contains:

1. Architecture v3.1
2. Data-audit record
3. Exact investable-universe specification
4. Development / Holdout A / Holdout B boundaries
5. Proxy Registry
6. PIT availability conventions
7. Missing-data policy
8. Historical sector-classification convention
9. Estimates inclusion/exclusion decision and vintage convention
10. Research provenance table
11. Primary signal-level metric
12. Primary portfolio-level metric
13. Statistical decision procedure
14. Multiplicity/dependence procedure
15. Transaction-cost model
16. Numeric specification budget
17. Specification-counting rules
18. Construct-level kill conditions
19. System-level kill condition
20. Rule #17 implementation
21. Rebalance-frequency convention
22. Holding-period convention
23. Frozen robustness alternatives
24. Environment manifest
25. Source-control/version information

Entry 001 is the:

> **No-more-free-decisions-before-results boundary.**

---

# 31. Exact Investable-Universe Artifact

Because the investable universe determines every cross-sectional rank and portfolio opportunity set, the Entry 001 package must explicitly state:

* eligible exchanges;
* listing types;
* eligible security types;
* security-type exclusions;
* liquidity / ADV rule;
* price floor, if any;
* minimum trading history;
* minimum fundamental history;
* required data sufficiency;
* sector-routing rules;
* entry date convention;
* exit date convention;
* treatment of newly listed companies;
* treatment of securities that cease satisfying investability requirements.

No universe rule is silently changed after observing return results.

---

# 32. Numeric Specification-Budget Artifact

Entry 001 must contain the actual numeric research budget for the cycle.

The artifact records:

* total specification count permitted;
* definition of one specification;
* examples of changes that consume one specification;
* examples of confirmed data/code corrections that do not count in the same way;
* logging procedure;
* procedure if the budget is exhausted.

The number is a governance commitment, not a universal statistical truth.

Its purpose is to impose a stopping rule before disappointment or excitement can influence how long the search continues.

---

# 33. Environment Manifest

The environment manifest itself is included inside the Entry 001 hash.

It includes at minimum:

* Python version;
* NumPy version;
* pinned dependency set;
* relevant analytical-library versions;
* operating/runtime environment where material;
* source-control commit hash;
* data-vendor/schema version where available.

This matters because specific computational behavior—such as the NumPy percentile implementation in Rule #17—is load-bearing for pass/fail decisions.

---

# 34. Specification Log

The log is append-only in spirit.

Every run records:

> timestamp → specification ID → code/version hash → data vintage → rationale → result → disposition.

Failed runs remain visible.

Confirmed data corrections remain visible.

Rules are not retrospectively rewritten to make the final path appear more linear or intentional than it was.

---

# 35. Final System Diagram

```
                 POINT-IN-TIME DATA
                         │
                         ▼
                 INVESTABLE UNIVERSE
                         │
                         ▼
              DETERMINISTIC FEATURE LIBRARY
                         │
       ┌─────────────────┼──────────────────┐
       │                 │                  │
       ▼                 ▼                  ▼
   VALUATION      BUSINESS ECONOMICS   CAPITAL ALLOCATION
       │                 │                  │
       ├─────────────────┼──────────────────┤
       │                 │                  │
       ▼                 ▼                  ▼
FUNDAMENTAL CHANGE  EXPECTATIONS CHANGE  MARKET CHANGE
       │                 │                  │
       └─────────────────┼──────────────────┘
                         │
              FRAGILITY / POSITIONING
                         │
                         ▼
          IDENTIFICATION & REDUNDANCY
                         │
          Standalone / Nested / Ablation
                         │
          Control-definition robustness
                         │
                         ▼
                  SIMPLE COMPOSITE
                         │
                         ▼
                    FINALIST SET
                   /           \
                  ▼             ▼
           REVERSE DCF       LLM EVIDENCE
                  \             /
                   ▼           ▼
                PORTFOLIO / EXITS
                         │
                         ▼
                    MONITORING
                         │
                         ▼
                SPECIFICATION LOG

```

---

# 36. Final Research Sequence

The remaining work proceeds in this order.

## Step 1 — Hash Entry 000

Freeze the architecture itself and establish that no strategy-return evidence was used in its construction.

## Step 2 — Audit the Data

Audit:

* fundamentals;
* prices;
* delistings;
* corporate actions;
* sector history;
* estimates;
* other intended datasets.

Negative findings receive full eight-field records.

## Step 3 — Determine Feasible Sample Structure

Using valid PIT coverage—not return performance—set:

* Development;
* Holdout A;
* Holdout B.

## Step 4 — Build the Proxy Registry

Enumerate exact frozen formulas.

Business Economics and Valuation are prioritized because they are expected to be important controls.

## Step 5 — Set Governance Choices

Freeze:

* exact universe rules;
* numeric specification budget;
* primary rebalance frequency;
* holding period;
* transaction-cost assumptions;
* permitted robustness variants.

## Step 6 — Build and Hash Entry 001

This creates the complete experimental freeze.

## Step 7 — Map the Existing Graham Screener

For every existing rule:

> rule → metric provenance → functional-form provenance → threshold provenance → sample exposure → economic construct → overlap → proposed disposition.

## Step 8 — Run the First Return Test

Only after Entry 001 exists.

---

# 37. Final Governing Principles

Architecture v3.1 can be summarized in the following principles.

> **Architecture defines which questions are allowed.**

> **Economic reasoning determines which hypotheses are worth testing.**

> **Point-in-time data determine which tests are actually possible.**

> **Audit findings determine the feasible experiment; they are not parameters to optimize.**

> **Evidence determines which features, constructs, and hypotheses survive.**

> **No dimension gets credit merely because it entered the model first.**

> **No dimension gets killed merely because it entered last.**

> **A failed implementation is not automatically a failed construct.**

> **A failed construct cannot be rescued by inventing new proxies after seeing results.**

> **An apparently incremental signal is not automatically an independent information source.**

> **A statistically detectable signal must also remain economically harvestable after realistic costs.**

> **Complexity earns admission only by demonstrating incremental value over simpler alternatives.**

> **LLMs extract evidence; deterministic code calculates financial signals.**

> **Negative data-audit findings are research results about what the system can legitimately establish.**

> **Holdout B is evidentiary capacity and is not spent merely because the usable sample is smaller than hoped.**

> **The Graham screener is historical input to the research question, not evidence for the answer.**

---

# 38. Status

**Architecture v3.1: CLOSED**

No further methodological modification is permitted without being explicitly recorded as a change.

The next research state is:

> **Entry 000 → Data Audit → Sample Definition → Proxy Registry → Governance Freeze → Entry 001 → Graham Mapping → First Return Test**
