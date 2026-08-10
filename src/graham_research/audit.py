"""Eight-field data-audit records required by Architecture v3.1."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from typing import Iterable

from .domain import AuditDecision, FactObservation


REALIZED_ACCOUNTING_FIELDS = frozenset({
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditures",
    "total_assets",
    "invested_capital",
    "income_tax_expense",
    "income_before_tax",
})

DERIVED_SOURCE_FIELDS = frozenset({
    "effective_tax_rate",
})


@dataclass(frozen=True)
class AuditFinding:
    finding: str
    evidence: str
    contamination_mechanism: str
    affected_construct_or_test: str
    eligibility_decision: AuditDecision
    sample_impact: str
    power_or_coverage_cost: str
    no_workaround_statement: str
    field: str | None = None
    admissible_after: date | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["eligibility_decision"] = self.eligibility_decision.value
        if self.admissible_after is not None:
            payload["admissible_after"] = self.admissible_after.isoformat()
        return payload


@dataclass(frozen=True)
class AuditReport:
    observations_checked: int
    securities_checked: int
    fields_checked: tuple[str, ...]
    findings: tuple[AuditFinding, ...]

    @property
    def has_exclusions(self) -> bool:
        return any(
            item.eligibility_decision is AuditDecision.EXCLUDED
            for item in self.findings
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "observations_checked": self.observations_checked,
            "securities_checked": self.securities_checked,
            "fields_checked": list(self.fields_checked),
            "has_exclusions": self.has_exclusions,
            "findings": [item.to_dict() for item in self.findings],
        }

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def audit_facts(facts: Iterable[FactObservation]) -> AuditReport:
    """Run structural checks without looking at strategy returns.

    This cannot prove that a vendor dataset is point-in-time. It identifies
    conditions that are independently sufficient to reject or restrict data.
    Vendor documentation and vintage sampling remain required evidence.
    """

    rows = tuple(facts)
    findings: list[AuditFinding] = []

    impossible_dates = [
        row for row in rows
        if row.field in REALIZED_ACCOUNTING_FIELDS
        and row.available_at.date() < row.period_end
    ]
    if impossible_dates:
        example = min(impossible_dates, key=lambda item: item.available_at)
        findings.append(AuditFinding(
            finding="Availability precedes the reported fiscal period end.",
            evidence=(
                f"{len(impossible_dates)} observations; example "
                f"{example.security_id}/{example.field}: period "
                f"{example.period_end}, available {example.available_at.isoformat()}."
            ),
            contamination_mechanism="The timestamp cannot represent public availability and permits future information.",
            affected_construct_or_test="Every feature using the affected observations.",
            eligibility_decision=AuditDecision.EXCLUDED,
            sample_impact="Affected observations must be removed from all samples.",
            power_or_coverage_cost=f"Loss of {len(impossible_dates)} observations.",
            no_workaround_statement="No engineering workaround can infer a valid publication timestamp from this contradiction.",
        ))

    derived_rows = [row for row in rows if row.field in DERIVED_SOURCE_FIELDS]
    if derived_rows:
        findings.append(AuditFinding(
            finding="A derived ratio was supplied through the source-fact layer.",
            evidence=(
                f"{len(derived_rows)} observations use derived field names: "
                f"{sorted({row.field for row in derived_rows})}."
            ),
            contamination_mechanism="Vendor-specific ratio definitions can bypass the frozen deterministic formula and change across vintages.",
            affected_construct_or_test="Business Economics and every proxy using the derived ratio.",
            eligibility_decision=AuditDecision.EXCLUDED,
            sample_impact="Replace the ratio with its reported numerator and denominator components.",
            power_or_coverage_cost=f"Loss of {len(derived_rows)} derived observations until components are available.",
            no_workaround_statement="The research layer must calculate the ratio; relabeling a vendor-derived value as a fact is not admissible.",
            field=derived_rows[0].field,
        ))

    identity = Counter(
        (
            row.security_id,
            row.field,
            row.period_end,
            row.available_at,
            row.accession,
        )
        for row in rows
    )
    duplicate_count = sum(count - 1 for count in identity.values() if count > 1)
    if duplicate_count:
        findings.append(AuditFinding(
            finding="Duplicate source observations were found.",
            evidence=f"{duplicate_count} duplicate rows share the same security, field, period, availability timestamp, and accession.",
            contamination_mechanism="Duplicates can overweight securities or create false revision histories.",
            affected_construct_or_test="Coverage statistics, feature calculations, and revision selection.",
            eligibility_decision=AuditDecision.ADMISSIBLE_RESTRICTED,
            sample_impact="Deduplicate by the full source identity before feature construction.",
            power_or_coverage_cost="No legitimate coverage loss when duplicates are exact.",
            no_workaround_statement="Exact identity deduplication is the only permitted correction; value-based aggregation is not valid.",
        ))

    units_by_series: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.unit:
            units_by_series[(row.security_id, row.field)].add(row.unit)
    mixed = {key: units for key, units in units_by_series.items() if len(units) > 1}
    if mixed:
        sample_key = sorted(mixed)[0]
        findings.append(AuditFinding(
            finding="A security-field series changes units.",
            evidence=f"{len(mixed)} affected series; example {sample_key} has {sorted(mixed[sample_key])}.",
            contamination_mechanism="Unconverted values create artificial level and change signals.",
            affected_construct_or_test="All level and change proxies using the affected fields.",
            eligibility_decision=AuditDecision.ADMISSIBLE_RESTRICTED,
            sample_impact="Use only periods with a frozen, verified unit conversion or exclude the series.",
            power_or_coverage_cost=f"Up to {len(mixed)} security-field histories may be lost.",
            no_workaround_statement="A verified conversion table is required; silently assuming equivalent units is prohibited.",
        ))

    revisions_without_accession = 0
    grouped: dict[tuple[str, str, date], list[FactObservation]] = defaultdict(list)
    for row in rows:
        grouped[(row.security_id, row.field, row.period_end)].append(row)
    for versions in grouped.values():
        if len(versions) > 1 and any(not row.accession for row in versions):
            revisions_without_accession += 1
    if revisions_without_accession:
        findings.append(AuditFinding(
            finding="Revision histories lack stable source identifiers.",
            evidence=f"{revisions_without_accession} revised security-field-period groups contain a missing accession.",
            contamination_mechanism="First-reported and restated values cannot be distinguished reproducibly.",
            affected_construct_or_test="PIT fact selection and every dependent proxy.",
            eligibility_decision=AuditDecision.EXCLUDED,
            sample_impact="Exclude affected histories unless immutable vendor vintage identifiers are obtained.",
            power_or_coverage_cost=f"Loss of {revisions_without_accession} revised period groups.",
            no_workaround_statement="Arrival order or value differences are not valid substitutes for provenance.",
        ))

    return AuditReport(
        observations_checked=len(rows),
        securities_checked=len({row.security_id for row in rows}),
        fields_checked=tuple(sorted({row.field for row in rows})),
        findings=tuple(findings),
    )
