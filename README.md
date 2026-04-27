# AI FlowOps

AI FlowOps is a portfolio-grade FastAPI application that demonstrates how a
commercial intake process can be converted into a governed AI operations workflow.

It combines:

- deterministic specialist agents,
- policy-based routing from a declarative playbook,
- human-in-the-loop approvals,
- persisted traces/evals/KPIs,
- and a server-rendered dashboard.

## Before vs After

### Manual baseline

- Unstructured intake review
- Rule-of-thumb escalations
- No auditable decision trail
- No deterministic routing policy

### AI FlowOps

- Structured intake package and normalized case file
- Deterministic evidence extraction and specialist findings
- Inspectable playbook rules and route decisions
- Explicit approval states (`pending`, `approved`, `rejected`, `override_route`,
  `request_info`)
- End-to-end traceability and KPIs

## Project Artifacts

- `docs/build-plan.md` — project scope and milestone plan
- `docs/architecture.md` — architecture narrative for reviewers
- `docs/demo-script.md` — demo walkthrough
- `docs/system-architecture.png` — architecture diagram
- `docs/human-in-the-loop.png` — HITL flow
- `schemas/` — domain models
- `agents/` — specialist agents
- `workflows/` — orchestration, playbooks, storage, and eval logic
- `app/` — FastAPI service, templates, and pages
- `data/seed/cases/` — 24 curated seed cases
- `data/held_out/cases/` — 5 held-out eval cases
- `evals/` — deterministic eval harness and outputs
- `scripts/` — CLI helpers

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Run app

```powershell
uvicorn app.main:app --reload
```

Then open: `http://127.0.0.1:8000`

### Run demo reset

```powershell
python scripts/demo_reset.py
```

### Run evals

```powershell
python scripts/run_evals.py
```

## Docker

```powershell
docker build -t ai-flowops .
docker run --rm -p 8000:8000 ai-flowops
```

Optional:

```powershell
docker compose up --build
```

Then open: `http://127.0.0.1:18080`

## QA Commands

```powershell
ruff check .
pytest
python scripts/demo_reset.py
python scripts/run_evals.py
git check-ignore -v docs/AI-Business-Operations-Orchestrator.md
```

## API Surface

- `GET /healthz`
- `GET /meta`
- `GET /api/cases`
- `POST /api/cases/seed`
- `POST /api/cases`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/run`
- `GET /api/approvals`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`
- `POST /api/approvals/{approval_id}/override`
- `POST /api/approvals/{approval_id}/request-info`
- `GET /api/kpis`
- `GET /api/evals`
- `POST /api/evals/run`
- `GET /api/traces/{case_id}`

## Pages

- `/` dashboard
- `/cases`
- `/cases/{case_id}`
- `/approvals`
- `/approvals/{approval_id}`
- `/evals`
- `/kpis`
- `/playbook`

## CI/CD

GitHub Actions validates:

- lint (`ruff`)
- tests (`pytest`)
- Docker build

Manual private VM deployment is available through the `deploy-vm` GitHub
Actions workflow. It connects to the VM over Tailscale + SSH, rebuilds only the
`ai-flowops-app` container, keeps the app bound to `127.0.0.1:18080`, and does
not copy `.env` files or AI credentials. See `docs/vm-deploy.md`.

## AI-assisted development disclosure

Built with AI-assisted development using ChatGPT/Codex for planning,
implementation, and evaluation support.

Raw planning artifacts are intentionally not published in tracked public docs.
