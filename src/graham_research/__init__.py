"""Systematic, point-in-time stock-selection research primitives."""

from .domain import (
    AuditDecision,
    DenominatorAction,
    DenominatorTransformation,
    FactObservation,
    FeatureExclusionReason,
    FeatureObservation,
    PeriodType,
    ProxyDefinition,
    ReportingFrequency,
    RestatementPolicy,
    RoleKind,
)

__all__ = [
    "AuditDecision",
    "DenominatorAction",
    "DenominatorTransformation",
    "FactObservation",
    "FeatureExclusionReason",
    "FeatureObservation",
    "PeriodType",
    "ProxyDefinition",
    "ReportingFrequency",
    "RestatementPolicy",
    "RoleKind",
]

__version__ = "0.2.3"
