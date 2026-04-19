# ADR-0001 Initial Architecture

## Context
Initial autonomous planning run.

## Decision
- Style: modular monolith + async workers
- Backend: Python API with role-based access control
- Frontend: Web dashboard
- Database: PostgreSQL
- Deployment: multi-environment deployment with staging and production
- Cloud target: aws

## Rationale
- Large but manageable volume balances simplicity and scalability.
- Modules can be extracted into services later with low migration risk.

## Consequences
- Enables deterministic phased delivery.
- Keeps decision records explicit for later autonomous revisions.
