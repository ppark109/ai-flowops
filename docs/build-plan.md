# AI FlowOps Build Plan

## Summary

AI FlowOps is a production-realistic portfolio demo for governed commercial
intake operations. Synthetic intake packages move through normalization,
evidence extraction, specialist review, deterministic playbook routing, human
approval, generated handoff artifacts, traces, KPIs, and deterministic evals.

The build prioritizes workflow integrity over feature breadth: public reviewers
can inspect the demo, but state-changing actions and raw payload access are
restricted to configured admin mode.

## Core Workflow

1. Load a synthetic intake package.
2. Normalize account, document, missing-info, and requirement fields.
3. Extract grounded evidence spans from intake, contract, order form,
   implementation notes, and security questionnaire text.
4. Run specialist review agents for legal, security, implementation, and
   finance risk.
5. Apply deterministic playbook rules and choose the authoritative route.
6. Create a pending approval when risk, uncertainty, missing information, or
   conflicts require human review.
7. Generate a brief and task handoff only after straight-through approval or a
   completed reviewer decision.
8. Persist traces, KPI records, and eval rows for inspection.

## Implementation Scope

- FastAPI app with server-rendered dashboard pages.
- SQLite persistence using standard library `sqlite3`.
- Pydantic schemas for workflow contracts.
- Deterministic fallback agents by default.
- Synthetic seed and held-out eval datasets.
- Docker packaging and local validation commands.
- Public documentation focused on architecture, demo flow, and validation.

## Security And Data Posture

- Synthetic data only.
- Public demo is read-only by default.
- Admin token is required for mutation routes, approval actions, eval runs, and
  raw case detail access.
- HTML admin forms include stateless CSRF-style tokens derived from the
  configured admin token and form action.
- Runtime databases, trace exports, eval outputs, secrets, caches, and local-only
  notes remain untracked.

## Validation

Use the same workflow paths that the app uses:

```powershell
python -m ruff check .
python -m pytest
python scripts/demo_reset.py
python scripts/run_evals.py
docker build -t ai-flowops .
```

## Acceptance Criteria

- Public pages render without external assets.
- Public API detail responses are redacted unless admin credentials are present.
- Mutation routes reject unauthenticated callers.
- Terminal cases cannot be reopened by rerunning the workflow.
- Approval decisions can only be applied to pending approvals.
- Deterministic routing cannot be overridden by request input.
- Eval output is written under ignored runtime storage.
- KPI and eval summaries are computed from persisted outcomes.
- Case lists filter by actual route, with expected route shown only as fixture
  reference data.
- Public docs remain concise and employer-readable.
