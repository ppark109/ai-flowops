# Demo Script: AI FlowOps

Use this as your reviewer walkthrough.

## 1) Reset the demo

```powershell
python scripts/demo_reset.py
```

This creates a clean runtime DB, loads 24 seed cases, and runs a representative sample through the workflow.

## 2) Open the dashboard

```powershell
uvicorn app.main:app --reload
```

Then open:

- `http://127.0.0.1:8000` dashboard overview
- `http://127.0.0.1:8000/cases` case list
- `http://127.0.0.1:8000/evals` eval table
- `http://127.0.0.1:8000/kpis` KPI view
- `http://127.0.0.1:8000/playbook` policy rules

## 3) Inspect a clean case

- Open any `expected_route = auto_approve` case.
- Verify evidence, route decision, and generated brief/tasks appear without approvals.

## 4) Inspect legal/security cases

- Open one legal and one security case.
- Confirm:
  - findings reference evidence.
  - route/approval decision is blocked for required review.
  - trace timeline shows normalization, evidence, specialists, playbook, routing, critic, and approval state.

## 5) Approve or override an approval

From `/approvals`, open a pending item:

- Approve: generates final approved outputs and updates status.
- Override route: choose an alternate route and continue.
- Request info: keeps unresolved and records missing info request.
- Reject: closes workflow without final implementation tasks.

## 6) Inspect trace and traces/evals

- Open `/cases/{case_id}` and verify the ordered trace timeline.
- Open `/evals` and confirm pass/fail metrics.
- Open `/kpis` for straight-through and escalation summary.

## 7) Optional smoke checks

```powershell
pytest
python scripts/run_evals.py
```

## 8) Run from container

```powershell
docker build -t ai-flowops .
docker run --rm -p 8000:8000 ai-flowops
```

Reviewer should be able to navigate all pages from the top navigation without external dependencies.
