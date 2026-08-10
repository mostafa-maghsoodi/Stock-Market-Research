"""Systematic, point-in-time stock-selection research primitives."""

from .domain import (
    AuditDecision,
    FactObservation,
    FeatureObservation,
    ProxyDefinition,
    RestatementPolicy,
)

__all__ = [
    "AuditDecision",
    "FactObservation",
    "FeatureObservation",
    "ProxyDefinition",
    "RestatementPolicy",
]

__version__ = "0.2.3"
