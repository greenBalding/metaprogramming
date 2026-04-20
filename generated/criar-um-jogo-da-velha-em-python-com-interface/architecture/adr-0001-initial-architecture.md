# ADR-0001 Initial Architecture

## Context
Initial autonomous planning run.

## Decision
- Style: modular monolith
- Backend: Python API
- Frontend: Web dashboard
- Database: PostgreSQL
- Deployment: multi-environment deployment with staging and production
- Cloud target: aws

## Rationale
- Fastest path to value for small and medium institutions.
- Operational complexity stays low while keeping clear module boundaries.

## Consequences
- Enables deterministic phased delivery.
- Keeps decision records explicit for later autonomous revisions.
