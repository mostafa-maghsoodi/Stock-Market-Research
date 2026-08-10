"""Point-in-time fact selection and contamination checks."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable, Iterator, Sequence

from .domain import FactObservation, RestatementPolicy


class PointInTimeViolation(ValueError):
    """Raised when a caller attempts to use information from the future."""


def decision_cutoff(decision_at: datetime) -> datetime:
    """Normalize an exact, timezone-aware decision timestamp to UTC."""

    if decision_at.tzinfo is None:
        raise ValueError("decision_at must be timezone-aware")
    return decision_at.astimezone(timezone.utc)


class PointInTimeStore:
    """In-memory reference implementation of historical fact selection.

    Production adapters can implement the same behavior in SQL. The explicit
    reference implementation is kept small enough to test exhaustively.
    """

    def __init__(self, facts: Iterable[FactObservation] = ()) -> None:
        self._facts: dict[tuple[str, str], list[FactObservation]] = defaultdict(list)
        for fact in facts:
            self.add(fact)

    def add(self, fact: FactObservation) -> None:
        bucket = self._facts[(fact.security_id, fact.field)]
        bucket.append(fact)
        bucket.sort(key=lambda item: (item.period_end, item.available_at))

    def versions(
        self,
        security_id: str,
        field: str,
        period_end: date,
    ) -> tuple[FactObservation, ...]:
        return tuple(
            fact
            for fact in self._facts.get((security_id, field), ())
            if fact.period_end == period_end
        )

    def history_as_of(
        self,
        security_id: str,
        field: str,
        as_of: datetime,
        policy: RestatementPolicy = RestatementPolicy.FIRST_REPORTED,
    ) -> tuple[FactObservation, ...]:
        cutoff = decision_cutoff(as_of)
        eligible = [
            fact
            for fact in self._facts.get((security_id, field), ())
            if fact.available_at <= cutoff
        ]
        by_period: dict[date, list[FactObservation]] = defaultdict(list)
        for fact in eligible:
            by_period[fact.period_end].append(fact)

        selected: list[FactObservation] = []
        for period_end, versions in by_period.items():
            ordered = sorted(versions, key=lambda item: item.available_at)
            selected.append(
                ordered[0]
                if policy is RestatementPolicy.FIRST_REPORTED
                else ordered[-1]
            )
        return tuple(sorted(selected, key=lambda item: item.period_end))

    def latest_as_of(
        self,
        security_id: str,
        field: str,
        as_of: datetime,
        policy: RestatementPolicy = RestatementPolicy.FIRST_REPORTED,
    ) -> FactObservation | None:
        history = self.history_as_of(security_id, field, as_of, policy)
        return history[-1] if history else None

    def require_known(
        self,
        fact: FactObservation,
        decision_at: datetime,
    ) -> None:
        if fact.available_at > decision_cutoff(decision_at):
            raise PointInTimeViolation(
                f"{fact.security_id}/{fact.field} was available at "
                f"{fact.available_at.isoformat()}, after {decision_at.isoformat()}"
            )

    def iter_facts(self) -> Iterator[FactObservation]:
        for key in sorted(self._facts):
            yield from self._facts[key]


def assert_no_future_facts(
    facts: Sequence[FactObservation], decision_at: datetime
) -> None:
    cutoff = decision_cutoff(decision_at)
    offenders = [fact for fact in facts if fact.available_at > cutoff]
    if offenders:
        first = min(offenders, key=lambda item: item.available_at)
        raise PointInTimeViolation(
            f"{len(offenders)} future fact(s); first is "
            f"{first.security_id}/{first.field} at {first.available_at.isoformat()}"
        )
