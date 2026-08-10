"""Boundary around the existing Graham.py live screener."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LegacySnapshotAssessment:
    ticker: str | None
    reusable_for_live_research: bool
    eligible_for_historical_backtest: bool
    reasons: tuple[str, ...]
    candidate_live_fields: tuple[str, ...]


def assess_graham_snapshot(snapshot: Mapping[str, Any]) -> LegacySnapshotAssessment:
    """Classify an output from the original ``Graham.py`` service.

    Its SEC Company Facts selector is useful for current mechanical research,
    but it does not provide a vendor-vintage panel or delisting returns. The
    snapshot must therefore never be silently admitted into a PIT backtest.
    """

    company = snapshot.get("company", {})
    metrics = snapshot.get("metrics", {})
    available = tuple(sorted(
        name for name, value in metrics.items()
        if value is not None and isinstance(value, (int, float))
    ))
    return LegacySnapshotAssessment(
        ticker=company.get("ticker"),
        reusable_for_live_research=bool(company and metrics),
        eligible_for_historical_backtest=False,
        reasons=(
            "The service resolves SEC facts from the current Company Facts response, not an immutable historical vendor vintage.",
            "Later 10-K comparative disclosures and amendments can supersede earlier values.",
            "The service has no survivorship-complete security master, delisted securities, or delisting returns.",
            "The caller supplies the current price; a historical adjusted-price and corporate-action panel is not present.",
        ),
        candidate_live_fields=available,
    )

