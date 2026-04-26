# AI FlowOps

AI FlowOps demonstrates how a manual commercial intake workflow can become a
governed, inspectable multi-agent AI process.  
The project is intentionally production-realistic and portfolio-oriented.

## Problem

Commercial intake typically combines contract text, order form details, implementation
notes, and security questionnaire signals across humans and static documents.
That makes routing decisions inconsistent and difficult to audit.

## AI Workflow

1. Intake package is normalized.
2. Evidence-backed snippets are extracted.
3. Specialist agents issue risk findings (legal, security, implementation, finance).
4. Deterministic playbook rules overlay the findings.
5. Critic and routing rules decide auto-approve vs approval-required.
6. HITL reviewers can approve, reject, override, or request more info.
7. Briefs, tasks, traces, KPIs, and eval records are persisted.

### Why this is useful for a portfolio

- Showcases deterministic policy over hidden prompt-only behavior.
- Demonstrates auditability (trace/eval/KPI) and HITL governance.
- Includes API + server-rendered UI, seeded synthetic data, scripts, CI, and Docker.

## Repository Structure

- `app/` FastAPI app, API routes, HTML pages, static assets.
- `agents/` Specialist deterministic agents with traceable outputs.
- `schemas/` Contracted data models for the workflow.
- `workflows/` Orchestrator, playbook loading, routing, and persistence.
- `playbooks/` YAML policy rules.
- `data/seed/cases` Synthetic seed cases (24 total).
- `data/held_out/cases` Reserved eval cases (5 total).
- `evals/` Deterministic evaluator and baseline artifacts.
- `scripts/` CLI tools for reset/seed/run/eval.
- `docs/` Public architecture and process documentation.

## Architecture and Visuals

- [Build plan](docs/build-plan.md)
- [Architecture overview](docs/architecture.md)
- [Demo script](docs/demo-script.md)
- `docs/system-architecture.png`
- `docs/human-in-the-loop.png`

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

uvicorn app.main:app --reload --port 8000
```

Open:

- `http://127.0.0.1:8000`

## CLI Commands

```powershell
python scripts/demo_reset.py
python scripts/run_evals.py
python scripts/run_case.py <case_id>
python scripts/seed_cases.py
python scripts/reset_db.py
```

## Validation Commands

```powershell
git status -sb
python -m ruff check .
pytest
python scripts/demo_reset.py
python scripts/run_evals.py
docker build -t ai-flowops .
```

## API and Dashboard

- API:
  - `GET /healthz`
  - `GET /meta`
  - `GET /api/cases`
  - `POST /api/cases/seed`
  - `POST /api/cases`
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
- Dashboard pages:
  - `/`, `/cases`, `/cases/{case_id}`, `/approvals`, `/approvals/{approval_id}`,
    `/evals`, `/kpis`, `/playbook`

## Docker

```powershell
docker build -t ai-flowops .
docker run --rm -p 8000:8000 ai-flowops
```

Optional:

```powershell
docker compose up --build
```

## AI Assistance Disclosure

Built with AI-assisted development using ChatGPT/Codex for planning, implementation,
and evaluation support.

This repo does not include real customer data or live production integrations in v1.
