"""Frozen schedule validation and holding-interval derivation."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimingError(ValueError):
    pass


TIMING_KEYS = frozenset({
    "calendar_basis",
    "rebalance_interval_count",
    "rebalance_date_convention",
    "month_end_convention",
    "schedule_anchor_date",
    "anchor_semantics",
    "holding_period_equals_rebalance_interval",
    "holding_period_rule",
    "holding_period_interval_count",
    "return_interval_start_rule",
    "return_interval_end_rule",
    "decision_information_cutoff",
    "portfolio_execution_timing",
    "return_measurement_start",
    "return_measurement_end",
    "market_session_basis",
    "market_timezone",
    "return_start_endpoint_inclusion",
    "return_end_endpoint_inclusion",
    "held_return_source_convention",
})

ECONOMIC_RETURN_CONVENTION_KEYS = frozenset({
    "decision_information_cutoff",
    "portfolio_execution_timing",
    "return_measurement_start",
    "return_measurement_end",
    "market_session_basis",
    "market_timezone",
    "return_start_endpoint_inclusion",
    "return_end_endpoint_inclusion",
    "held_return_source_convention",
})
ECONOMIC_RETURN_DESCRIPTOR_FIELDS = frozenset({
    "decision_information_cutoff",
    "portfolio_execution_timing",
    "return_measurement_start",
    "return_measurement_end",
    "market_session_basis",
    "held_return_source_convention",
})

SUPPORTED_CALENDAR_BASES = frozenset({"calendar_days", "calendar_months"})
SUPPORTED_REBALANCE_CONVENTIONS = frozenset({
    "calendar_month_end",
    "calendar_quarter_end",
    "fixed_n_calendar_days",
})
SUPPORTED_ANCHOR_SEMANTICS = frozenset({"first_valid_date", "cadence_epoch"})
SUPPORTED_HOLDING_RULES = frozenset({
    "rebalance_interval",
    "fixed_calendar_days",
    "fixed_calendar_months",
})


def _last_day(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(index, 12)
    month = zero_month + 1
    return _last_day(year, month)


@dataclass(frozen=True)
class HoldingInterval:
    period_start: date
    period_end: date

    def __post_init__(self) -> None:
        if self.period_end <= self.period_start:
            raise TimingError("holding interval must end after it starts")


@dataclass(frozen=True)
class ResolvedPortfolioTiming:
    calendar_basis: str
    rebalance_interval_count: int
    rebalance_date_convention: str
    month_end_convention: str
    schedule_anchor_date: date | None
    anchor_semantics: str | None
    holding_period_equals_rebalance_interval: bool
    holding_period_rule: str
    holding_period_interval_count: int | None
    return_interval_start_rule: str
    return_interval_end_rule: str
    decision_information_cutoff: str
    portfolio_execution_timing: str
    return_measurement_start: str
    return_measurement_end: str
    market_session_basis: str
    market_timezone: str
    return_start_endpoint_inclusion: str
    return_end_endpoint_inclusion: str
    held_return_source_convention: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResolvedPortfolioTiming":
        missing = sorted(TIMING_KEYS - set(value))
        extra = sorted(set(value) - TIMING_KEYS)
        if missing or extra:
            raise TimingError(
                f"portfolio_timing has invalid keys; missing={missing}, extra={extra}"
            )
        basis = value["calendar_basis"]
        convention = value["rebalance_date_convention"]
        count = value["rebalance_interval_count"]
        if basis not in SUPPORTED_CALENDAR_BASES:
            raise TimingError("portfolio_timing calendar_basis is unsupported")
        if convention not in SUPPORTED_REBALANCE_CONVENTIONS:
            raise TimingError("portfolio_timing rebalance convention is unsupported")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise TimingError("rebalance_interval_count must be a positive integer")
        if convention == "fixed_n_calendar_days":
            if basis != "calendar_days":
                raise TimingError("fixed_n_calendar_days requires calendar_days")
            try:
                anchor_date = date.fromisoformat(str(value["schedule_anchor_date"]))
            except (TypeError, ValueError) as exc:
                raise TimingError("fixed schedules require schedule_anchor_date") from exc
            anchor_semantics = value["anchor_semantics"]
            if anchor_semantics not in SUPPORTED_ANCHOR_SEMANTICS:
                raise TimingError("fixed schedules require resolved anchor_semantics")
            if value["month_end_convention"] != "not_applicable":
                raise TimingError("fixed calendar-day schedules require no month-end rule")
        else:
            if basis != "calendar_months" or count != 1:
                raise TimingError(
                    "calendar-anchored month/quarter schedules require interval count 1"
                )
            if value["month_end_convention"] != "civil_calendar_month_end":
                raise TimingError("calendar month schedules require civil month end")
            if value["schedule_anchor_date"] != "not_applicable":
                raise TimingError("calendar-anchored schedules forbid an anchor")
            if value["anchor_semantics"] != "not_applicable":
                raise TimingError("calendar-anchored schedules forbid anchor semantics")
            anchor_date = None
            anchor_semantics = None

        equals = value["holding_period_equals_rebalance_interval"]
        if not isinstance(equals, bool):
            raise TimingError(
                "holding_period_equals_rebalance_interval must be boolean"
            )
        holding_rule = value["holding_period_rule"]
        if holding_rule not in SUPPORTED_HOLDING_RULES:
            raise TimingError("holding_period_rule is unsupported")
        holding_count_value = value["holding_period_interval_count"]
        if equals:
            if holding_rule != "rebalance_interval":
                raise TimingError("equal holding period requires rebalance_interval rule")
            if holding_count_value != "not_applicable":
                raise TimingError("equal holding period forbids a separate interval count")
            holding_count = None
        else:
            raise TimingError(
                "unequal holding and rebalance intervals are not executable "
                "without governed overlapping-lot or cash-gap portfolio-state rules"
            )
        if value["return_interval_start_rule"] != "decision_date":
            raise TimingError("unsupported return-interval start rule")
        expected_end = "next_scheduled_decision_date"
        if value["return_interval_end_rule"] != expected_end:
            raise TimingError("return-interval end rule conflicts with holding rule")
        for name in ECONOMIC_RETURN_DESCRIPTOR_FIELDS:
            if not isinstance(value[name], str) or not value[name].strip():
                raise TimingError(
                    f"portfolio_timing.{name} must be an explicit non-empty "
                    "researcher-approved convention descriptor"
                )
        for name in (
            "return_start_endpoint_inclusion",
            "return_end_endpoint_inclusion",
        ):
            if value[name] not in {"included", "excluded"}:
                raise TimingError(f"portfolio_timing.{name} is unsupported")
        market_timezone = value["market_timezone"]
        if not isinstance(market_timezone, str) or not market_timezone.strip():
            raise TimingError("portfolio_timing.market_timezone must be an IANA zone")
        try:
            ZoneInfo(market_timezone)
        except ZoneInfoNotFoundError as exc:
            raise TimingError(
                "portfolio_timing.market_timezone must be an IANA zone"
            ) from exc
        return cls(
            calendar_basis=basis,
            rebalance_interval_count=count,
            rebalance_date_convention=convention,
            month_end_convention=value["month_end_convention"],
            schedule_anchor_date=anchor_date,
            anchor_semantics=anchor_semantics,
            holding_period_equals_rebalance_interval=equals,
            holding_period_rule=holding_rule,
            holding_period_interval_count=holding_count,
            return_interval_start_rule=value["return_interval_start_rule"],
            return_interval_end_rule=value["return_interval_end_rule"],
            decision_information_cutoff=value["decision_information_cutoff"],
            portfolio_execution_timing=value["portfolio_execution_timing"],
            return_measurement_start=value["return_measurement_start"],
            return_measurement_end=value["return_measurement_end"],
            market_session_basis=value["market_session_basis"],
            market_timezone=market_timezone,
            return_start_endpoint_inclusion=value[
                "return_start_endpoint_inclusion"
            ],
            return_end_endpoint_inclusion=value["return_end_endpoint_inclusion"],
            held_return_source_convention=value["held_return_source_convention"],
        )

    def economic_return_convention(self) -> Mapping[str, str]:
        """Return the exact convention an audited held-return source must attest."""

        return {
            name: str(getattr(self, name))
            for name in sorted(ECONOMIC_RETURN_CONVENTION_KEYS)
        }

    def is_valid_decision_date(self, value: date) -> bool:
        if self.rebalance_date_convention == "calendar_month_end":
            return value == _last_day(value.year, value.month)
        if self.rebalance_date_convention == "calendar_quarter_end":
            return value.month in {3, 6, 9, 12} and value == _last_day(
                value.year, value.month
            )
        assert self.schedule_anchor_date is not None
        delta = (value - self.schedule_anchor_date).days
        if self.anchor_semantics == "first_valid_date" and delta < 0:
            return False
        return delta % self.rebalance_interval_count == 0

    def next_scheduled_date(self, value: date) -> date:
        if not self.is_valid_decision_date(value):
            raise TimingError(f"invalid decision date under frozen schedule: {value}")
        if self.rebalance_date_convention == "calendar_month_end":
            return _add_months(value, 1)
        if self.rebalance_date_convention == "calendar_quarter_end":
            return _add_months(value, 3)
        return value + timedelta(days=self.rebalance_interval_count)

    def holding_interval(self, value: date) -> HoldingInterval:
        if not self.is_valid_decision_date(value):
            raise TimingError(f"invalid decision date under frozen schedule: {value}")
        if self.holding_period_equals_rebalance_interval:
            end = self.next_scheduled_date(value)
        elif self.holding_period_rule == "fixed_calendar_days":
            assert self.holding_period_interval_count is not None
            end = value + timedelta(days=self.holding_period_interval_count)
        else:
            assert self.holding_period_interval_count is not None
            end = _add_months(value, self.holding_period_interval_count)
        return HoldingInterval(value, end)

    def schedule_between(
        self,
        start: date,
        end: date,
        *,
        start_included: bool,
        end_included: bool,
    ) -> tuple[date, ...]:
        if end < start:
            raise TimingError("sample partition ends before it starts")
        if self.rebalance_date_convention == "fixed_n_calendar_days":
            assert self.schedule_anchor_date is not None
            cursor = self.schedule_anchor_date
            if self.anchor_semantics == "cadence_epoch":
                delta = (start - cursor).days
                steps = delta // self.rebalance_interval_count
                cursor += timedelta(days=steps * self.rebalance_interval_count)
                while cursor < start:
                    cursor += timedelta(days=self.rebalance_interval_count)
            else:
                while cursor < start:
                    cursor += timedelta(days=self.rebalance_interval_count)
        else:
            cursor = _last_day(start.year, start.month)
            if self.rebalance_date_convention == "calendar_quarter_end":
                while cursor.month not in {3, 6, 9, 12}:
                    cursor = _add_months(cursor, 1)
        output: list[date] = []
        while cursor < end or (end_included and cursor == end):
            after_start = cursor > start or (start_included and cursor == start)
            if after_start and self.is_valid_decision_date(cursor):
                output.append(cursor)
            cursor = self.next_scheduled_date(cursor)
        return tuple(output)


def parse_decision_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise TimingError(f"invalid decision_date: {value!r}") from exc
