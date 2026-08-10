# ADR-003 — Outcome-free screen and outcome-governance boundary

## ADR ID

`ADR-003`

## Title

Outcome-free screen and outcome-governance boundary

## Status

FINAL — approval state is external to these bytes. This document does not
self-attest approval. Governing effect is determined only by the applicable
external Approval Record identity and human approval process.

## Decision

Outcome-free screen construction consumes no outcome-research specification
slot and requires no OPEN/CLOSE.

Any realized-outcome evaluation still requires:

`full Entry001 → specification budget → durable OPEN → authorized outcome-bearing execution → CLOSE`

Future Entry001 must bind the exact screen/ranking/candidate lineage.

## Scope

The decision separates outcome-free screen construction from the unchanged
Run 2 boundary for every realized-outcome evaluation.

## What this decision does NOT authorize

It does not authorize outcome access, weaken Entry001, budget, OPEN/CLOSE, or
lineage requirements, or select any implementation or research value.

## Relationship to Architecture v3.2

Architecture v3.2 carries this boundary into the successor architecture.

## Relationship to Amendment Ledger

This ADR is an independently addressable decision subject for the first
Amendment Ledger.

## Relationship to Entry000

Entry000 binds this ADR's approval evidence through the approved Amendment
Ledger; the ADR is not an additional member of the six-component array.

## Researcher approval boundary

Preliminary authorization to prepare this subject is not governing approval.
Governing approval occurs only after these exact subject bytes are committed,
an Approval Record identifying their path/source-commit/blob/SHA-256 is created
and committed, and the researcher explicitly approves that exact committed
Approval Record identity.
