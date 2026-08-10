"""The universal boundary between durable OPEN and governed outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .specification import OpenedSpecification, RunType, SpecificationRegister

if TYPE_CHECKING:
    from .backtest import BacktestResult, PreparedPortfolioExperiment


def execute_opened_experiment(
    opened: OpenedSpecification,
    prepared: "PreparedPortfolioExperiment",
    register: SpecificationRegister,
) -> "BacktestResult":
    """Validate an internal OPEN capability, execute, and append CLOSE.

    ``portfolio_backtest`` is the only supported governed outcome-producing run
    type in this MVP. Public mathematical IC/triad/Rule-17 helpers remain
    ungoverned utilities and cannot emit a governed result artifact.
    """

    authorization = register._authorize_execution(opened, prepared)
    if opened.run_type is not RunType.PORTFOLIO_BACKTEST:
        raise TypeError("unsupported governed run type")
    from .backtest import (
        OutcomeAccountingError,
        _produce_portfolio_results_after_open,
    )

    try:
        result = _produce_portfolio_results_after_open(
            authorization,
            opened,
            prepared,
        )
    except OutcomeAccountingError as exc:
        register._close(
            opened,
            status="failed",
            failure_classification="post_open_outcome_accounting_failure",
            failure_message=str(exc),
        )
        raise
    except Exception as exc:
        register._close(
            opened,
            status="failed",
            failure_classification="infrastructure_or_software_failure",
            failure_message=str(exc),
        )
        raise
    register._close(opened, status="completed")
    return result
