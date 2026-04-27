# AI FlowOps Build Plan

## Summary

Build `AI FlowOps` as a complete clickable portfolio demo that shows how a manual commercial intake workflow can become a governed multi-agent AI operations workflow. The first full build must be end-to-end: synthetic intake cases enter the system, specialist agents produce evidence-backed findings, deterministic playbook rules route the case, risky/uncertain work pauses for human review, approved cases generate implementation briefs/tasks, and the system records traces, KPI records, and eval results.

The implementation target is a production-realistic local demo with FastAPI, server-rendered dashboard pages, SQLite persistence, deterministic fallback agents, CI, and Docker packaging. Do not deploy to the VM in this build. Do not add real enterprise integrations, auth, OCR, or CUAD ingestion yet.

Create this source-of-truth public document at `docs/build-plan.md`. Also create a cleaner public architecture doc at `docs/architecture.md`. Keep the raw ChatGPT research report ignored locally and do not commit it.

## Operating Rules For Spark

- Work from `C:\dev\ai-flowops`.
- Create a branch named `codex/build-ai-flowops-demo`.
- Build in milestone order. Do not skip tests between milestones.
- Commit after each stable milestone with a clear message.
- Preserve the ignored local file `docs/AI-Business-Operations-Orchestrator.md`; do not track, delete, rename, or quote it.
- Keep tests production-realistic. Do not weaken tests, mock away core behavior, or change expected outcomes just to pass.
- Favor deterministic code for routing, policy, persistence, approvals, KPI math, and eval scoring.
- Use AI-capable interfaces, but make deterministic fallback agents the default for tests and local demo reliability.
- Keep the public app simple, inspectable, and employer-readable. The strongest signal is governed workflow quality, not visual complexity.

## Milestone 0: Repo And Planning Docs

Goal: make the repo explainable before adding product code.

Implement:

- Add `docs/build-plan.md` with this plan.
- Add `docs/architecture.md` as the polished public project overview.
- Update `README.md` to reference:
  - problem statement
  - demo workflow
  - architecture diagram
  - local setup
  - test/CI commands
  - Docker commands
  - docs links
- Keep public docs clean:
  - tracked: `docs/build-plan.md`, `docs/architecture.md`, `docs/system-architecture.png`, `docs/human-in-the-loop.png`
  - ignored only: `docs/AI-Business-Operations-Orchestrator.md`

Architecture doc must explain:

- Manual process before AI FlowOps.
- AI workflow after AI FlowOps.
- The multi-agent roles.
- Why deterministic playbook routing surrounds AI outputs.
- HITL approval behavior.
- Trace/eval/KPI story.
- MVP limits: synthetic data first, no real integrations, no auth, no OCR, no CUAD in v1.

Validation:

- `git status -sb`
- `git check-ignore -v docs/AI-Business-Operations-Orchestrator.md`
- `ruff check .`
- `pytest`

Commit: `docs: add AI FlowOps build and architecture plan`

## Milestone 1: Core Domain Models

Goal: define the workflow contract before building behavior.

Add or expand Pydantic schemas for:

- Intake package:
  - `case_id`
  - customer/account fields
  - submitted timestamp
  - intake email text
  - contract text
  - order form text
  - implementation notes
  - security questionnaire text
  - optional metadata
- Normalized case file:
  - normalized account info
  - document refs
  - extracted customer requirements
  - missing info list
  - package completeness status
- Evidence:
  - source document type
  - locator
  - quote
  - normalized fact
  - confidence
- Finding:
  - finding id
  - rule id
  - finding type
  - severity
  - route
  - summary
  - evidence list
  - confidence
- Routing decision:
  - recommended route
  - confidence
  - approval required
  - reasons
  - triggered rules
- Approval:
  - approval id
  - case id
  - status: pending, approved, rejected, override_route, request_info
  - reviewer
  - comments
  - original route
  - final route
  - created/resolved timestamps
- Generated outputs:
  - implementation brief
  - task list
  - task owner
  - task due category
  - source finding ids
- Trace record:
  - case id
  - step name
  - inputs summary
  - outputs summary
  - model/provider label
  - latency placeholder
  - token/cost placeholder
  - created timestamp
- Eval result:
  - case id
  - expected route
  - actual route
  - route pass/fail
  - grounding pass/fail
  - approval pass/fail
  - brief completeness score
  - notes
- KPI record:
  - case id
  - final route
  - straight-through boolean
  - approval required boolean
  - reviewer override boolean
  - processing time placeholder
  - generated task count

Implementation guidance:

- Keep schema files under `schemas/`.
- Use strict-enough validation for required fields and route/status enums.
- Do not over-engineer inheritance.
- Use simple explicit models instead of dynamic dictionaries except for narrow metadata fields.

Validation tests:

- Valid sample intake package validates.
- Invalid route is rejected.
- Approval status enum rejects unknown values.
- Trace/eval/KPI records validate with minimum required fields.
- Existing tests continue passing.

Commit: `feat: define core workflow schemas`

## Milestone 2: Synthetic Dataset

Goal: create realistic demo/eval cases without external dependencies.

Create 24 curated synthetic cases under `data/seed/cases/`.

Case distribution:

- 5 clean low-risk cases
- 5 legal-risk cases
- 5 security-risk cases
- 5 implementation-risk cases
- 4 finance-risk cases

Each case should be a JSON file with:

- intake package fields
- expected route
- expected approval requirement
- expected key risk labels
- expected task owner category
- short human-readable scenario summary

Use realistic but fake company names and no real customer data.

Scenario examples:

- Clean: standard MSA, supported CRM integration, complete order form, normal go-live.
- Legal: liability cap above standard, nonstandard indemnity, unusual termination clause.
- Security: missing DPA, regulated data, data residency request, incomplete security questionnaire.
- Implementation: aggressive go-live, unsupported integration, unclear customer owner, dependency conflict.
- Finance: large discount, SLA credits, custom billing terms, unusual penalty exposure.

Also create:

- `data/held_out/cases/` with 5 held-out cases, one per route family.
- `data/seed/README.md` explaining case format.
- `data/held_out/README.md` explaining eval-only use.

Validation tests:

- Every seed and held-out JSON file loads.
- Every case validates against the intake schema.
- Every case has expected route and expected approval requirement.
- There are exactly 24 seed cases and 5 held-out cases.
- No seed case contains obvious placeholder text like `TODO`, `lorem`, or `example.com`.

Commit: `feat: add synthetic intake dataset`

## Milestone 3: Playbook Rules And Loader

Goal: make business policy inspectable and deterministic.

Expand `playbooks/default.yaml` to 12-15 rules covering:

- liability cap above standard
- nonstandard indemnity
- missing DPA
- data residency request
- regulated data without security artifact
- aggressive go-live date
- unsupported integration
- unclear customer owner
- missing SOW
- discount above threshold
- custom SLA credits
- unusual penalty terms
- clean standard package
- conflicting terms
- incomplete intake package

Each rule must include:

- id
- description
- route
- severity
- approval_required
- deterministic matching hints
- required evidence types
- task template

Implement playbook validation:

- duplicate rule ids fail
- unsupported route fails
- missing description fails
- high/critical severity must require approval
- every non-auto route has at least one rule
- at least one clean auto-approve rule exists

Implementation guidance:

- Keep matching simple for v1: phrase/field heuristics are acceptable.
- Do not use AI for final rule application.
- Rule output should include rule id, route, severity, and required evidence.

Validation tests:

- Default playbook loads.
- Invalid fixture playbooks fail for duplicate id, invalid route, and high severity without approval.
- Default playbook covers all five MVP routes.
- Rule count is between 12 and 15.

Commit: `feat: expand and validate playbook rules`

## Milestone 4: SQLite Persistence

Goal: persist workflow state so the dashboard and approvals are real.

Implement a small SQLite persistence layer using the standard library `sqlite3`.

Tables:

- `cases`
- `documents`
- `findings`
- `routing_decisions`
- `approvals`
- `generated_outputs`
- `tasks`
- `trace_records`
- `eval_results`
- `kpi_records`

Implementation guidance:

- Store structured payloads as JSON text where that keeps the schema simple.
- Use explicit timestamps.
- Keep migrations simple: one `schema.sql` or Python initializer that creates tables if missing.
- Default DB path: `data/runtime/app.sqlite3`.
- Tests should use temporary SQLite files, not the real runtime DB.
- Do not introduce SQLAlchemy unless there is a strong reason.

Required repository behavior:

- `data/runtime/` remains ignored except `.gitkeep`.
- Seed loading should be repeatable.
- Re-running the seed loader should not create duplicate cases.

Validation tests:

- DB initializes from empty file.
- Seed cases insert and can be listed.
- One full case with findings, routing, approval, outputs, traces, eval, and KPI can be saved and read back.
- Re-seeding is idempotent.

Commit: `feat: add sqlite persistence and seed loading`

## Milestone 5: Agent Interfaces And Deterministic Fallback Agents

Goal: showcase multi-agent orchestration without flaky model dependency.

Create agent modules under `agents/` for:

- Intake Normalization Agent
- Evidence Extraction Agent
- Contract Risk Agent
- Security Review Agent
- Implementation Review Agent
- Finance Review Agent
- Routing Recommendation Agent
- Brief Generation Agent
- Task Generation Agent
- Critic/Evaluator Agent

Each agent should have:

- a clear class or function entrypoint
- typed input/output schemas
- a `provider` label
- a deterministic fallback implementation
- trace emission around its work

Default local/test mode:

- Use deterministic fallback agents.
- Detect risk using explicit phrases and fields in synthetic cases.
- Return evidence quotes from the source text.
- Never invent evidence.

API-capable mode:

- Add an abstraction that can later call OpenAI/Agents SDK.
- Read settings from environment.
- Keep real model calls disabled by default unless explicitly configured.
- If API mode is not configured, fall back deterministically.

Implementation guidance:

- Do not hardcode one giant “agent.”
- The orchestrator must call multiple specialist agents in sequence.
- Specialist agents may be deterministic in v1, but their boundaries must be visible in code, traces, and UI.
- Avoid pretending a model ran when fallback mode ran. Label fallback traces as `deterministic-fallback`.

Validation tests:

- Each agent can run on at least one fixture.
- Evidence agent returns quotes actually present in source text.
- Risk agents return expected risk labels for representative cases.
- Critic flags missing evidence.
- Trace records show multiple agent steps for one case.

Commit: `feat: add multi-agent fallback workflow interfaces`

## Milestone 6: End-To-End Orchestrator

Goal: wire the business process from intake submission to final pending/approved output.

Build workflow orchestration under `workflows/`.

End-to-end flow:

1. Accept intake package.
2. Normalize into case file.
3. Extract evidence.
4. Run specialist agents:
   - contract/legal
   - security
   - implementation
   - finance
5. Apply playbook rules deterministically.
6. Score severity/confidence.
7. Produce routing decision.
8. Run critic/evaluator check.
9. If low-risk/high-confidence: auto-approve and generate outputs.
10. If risky/low-confidence/missing info: create pending approval.
11. Persist every step.
12. Emit traces and KPI records.

Routing rules:

- Auto-approve only when clean package, low severity, complete info, and sufficient confidence.
- Legal route for legal/contract deviations.
- Security route for missing DPA, regulated data, data residency, security questionnaire issues.
- Implementation route for go-live/integration/owner/dependency problems.
- Finance route for discounts, credits, penalties, billing exceptions.
- If multiple specialist risks exist, choose highest severity route and record secondary risks.
- High severity always requires approval.
- Low confidence requires approval.
- Missing required info requires approval.
- Contradictory evidence requires approval.

Implementation guidance:

- Keep final route deterministic after agent outputs.
- Store both agent recommendation and final rule-based decision.
- Return a single workflow result object suitable for API and UI.
- Do not send emails or create real external tasks.

Validation tests:

- All 24 seed cases run end-to-end.
- Expected route accuracy is high enough for deterministic seed cases: 24/24.
- Expected approval requirement accuracy: 24/24.
- Auto-approved cases generate briefs/tasks immediately.
- Approval-required cases create pending approval and do not create final approved outputs until approval.
- Trace count per case includes multiple named agent/workflow steps.

Commit: `feat: implement end-to-end orchestration`

## Milestone 7: Approval Workflow

Goal: make HITL behavior real and inspectable.

Implement approval operations:

- list pending approvals
- view approval detail
- approve
- reject
- override route
- request more information
- add reviewer comment
- resume workflow after approval/override
- record final decision log

Behavior:

- Approve: generate implementation brief/tasks using recommended route.
- Reject: mark case rejected, do not generate implementation tasks.
- Override route: record original route and final route, then generate outputs for final route.
- Request info: keep case unresolved and record missing info request.
- Comments: required for reject and override; optional for approve.

Validation tests:

- Pending approval can be approved and resumed.
- Override route changes final route and records reviewer override.
- Reject does not create tasks.
- Request-info keeps approval unresolved.
- KPI record reflects straight-through vs approval vs override.

Commit: `feat: add human approval workflow`

## Milestone 8: Brief And Task Generation

Goal: convert AI/routing findings into operational handoff artifacts.

Implementation brief must include:

- case summary
- customer/account summary
- final route
- risk summary
- evidence-backed findings
- missing info
- implementation considerations
- approval decision summary
- recommended next steps

Task generation must produce:

- title
- owner function
- priority
- due category
- source finding ids
- evidence references
- status

Task behavior:

- Clean cases produce onboarding tasks.
- Legal cases produce legal review/resolution tasks.
- Security cases produce DPA/security/data handling tasks.
- Implementation cases produce feasibility/dependency/owner tasks.
- Finance cases produce pricing/approval/commercial review tasks.

Validation tests:

- Every auto-approved or approved case has a brief.
- Every generated task links to route or finding.
- High-risk cases include evidence in the brief.
- Rejected/request-info cases do not produce final implementation tasks.

Commit: `feat: generate implementation briefs and tasks`

## Milestone 9: FastAPI API Surface

Goal: expose the workflow cleanly for UI and tests.

Add API routes:

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

Implementation guidance:

- Keep API JSON shapes based on Pydantic schemas.
- Return useful 404/400 errors.
- Do not expose secrets or raw environment data.
- Keep route handlers thin; business logic stays in workflows/services.

Validation tests:

- API can seed cases.
- API can run one case.
- API can approve pending case.
- API returns KPI summary.
- API returns trace list for a case.
- OpenAPI generation does not fail.

Commit: `feat: expose workflow API`

## Milestone 10: Server-Rendered Dashboard

Goal: make the portfolio demo clickable without React complexity.

Use FastAPI templates/static assets.

Pages:

- `/`
  - dashboard overview
  - total cases
  - pending approvals
  - straight-through rate
  - route distribution
  - eval pass summary
- `/cases`
  - table of cases
  - route/status badges
  - approval status
  - search/filter by route/status
- `/cases/{case_id}`
  - intake summary
  - documents
  - evidence
  - findings
  - rule hits
  - routing decision
  - approval state
  - generated brief
  - tasks
  - trace timeline
- `/approvals`
  - pending approval queue
- `/approvals/{approval_id}`
  - approval packet
  - evidence
  - recommendation
  - approve/reject/override/request-info form
- `/evals`
  - held-out eval result table
  - pass/fail summary
- `/kpis`
  - route counts
  - straight-through rate
  - escalation rate
  - override rate
  - average generated task count
- `/playbook`
  - list of rules and routes
  - read-only policy transparency view

UI guidance:

- Keep style restrained and operational.
- No marketing hero page.
- Use dense, readable tables and detail panels.
- Do not put cards inside cards.
- Avoid giant decorative sections.
- Use clear route/status badges.
- Every case detail should make evidence/rule/route/approval trace inspectable.
- Dashboard should be useful for a technical reviewer, not just attractive.

Validation tests:

- Main pages return 200.
- Seeded data appears in cases page.
- Approval form actions work.
- Case detail includes evidence, route, and trace sections.
- No page requires external network assets.

Commit: `feat: add server-rendered review dashboard`

## Milestone 11: Eval Harness

Goal: prove the AI workflow does not regress.

Implement eval runner under `evals/` and/or `workflows/evals.py`.

Eval inputs:

- `data/held_out/cases/`
- optionally all seed cases for local smoke eval

Scorers:

- route accuracy
- approval requirement accuracy
- evidence grounding
- brief completeness
- no unsupported hallucination
- task usefulness basics
- trace completeness

Baseline outputs:

- JSON result file under `evals/baselines/`
- Summary table in dashboard
- KPI/eval records persisted to DB

CI behavior:

- Deterministic seed/held-out evals run in normal CI.
- Real model evals are not required in normal CI.
- If API mode is later enabled, put model evals behind manual workflow or nightly workflow.

Pass thresholds for v1 deterministic build:

- route accuracy: 100% on seed and held-out synthetic cases
- approval requirement accuracy: 100%
- evidence grounding: 100% quotes found in source text
- brief exists for all approved/auto-approved cases
- trace completeness: at least normalization, evidence, specialist review, playbook, routing, critic, and output/approval step

Validation tests:

- Eval runner produces result JSON.
- Eval runner fails when expected route is intentionally wrong in a test fixture.
- Dashboard/API can read eval summaries.
- CI runs deterministic eval.

Commit: `feat: add deterministic eval harness`

## Milestone 12: Traceability And KPI Reporting

Goal: make reviewer inspection and business-value framing concrete.

Trace timeline must show:

- step name
- agent/module name
- provider/mode
- input summary
- output summary
- created timestamp
- related case id

KPI summary must calculate:

- total cases
- straight-through processing rate
- escalation rate
- route distribution
- approval queue count
- override rate
- rejected count
- request-info count
- average generated tasks per completed case
- eval pass rate

Implementation guidance:

- KPI math should be computed from persisted records.
- Do not hardcode KPI numbers in UI.
- Use deterministic timestamps only in tests where needed.
- Show both operational and eval metrics.

Validation tests:

- KPI summary from known fixture cases matches expected counts.
- Trace list preserves workflow order.
- Case detail page shows trace timeline.

Commit: `feat: add trace and KPI reporting`

## Milestone 13: CLI Scripts

Goal: make the app easy to reset, seed, and evaluate.

Add scripts:

- `scripts/reset_db.py`
- `scripts/seed_cases.py`
- `scripts/run_case.py`
- `scripts/run_evals.py`
- `scripts/demo_reset.py`

Behavior:

- `demo_reset.py` should create a clean runtime DB, seed all cases, run a representative subset or all cases, and leave approvals visible.
- Scripts should use the same workflow code as the app.
- Scripts should be safe to rerun.

Validation:

```powershell
python scripts/demo_reset.py
python scripts/run_evals.py
pytest
```

Commit: `feat: add demo and eval scripts`

## Milestone 14: Docker Packaging

Goal: prove the app can run outside the local Python environment.

Add:

- `Dockerfile`
- `.dockerignore`
- optional `docker-compose.yml` for local demo

Container behavior:

- install project
- expose port `8000`
- run FastAPI with uvicorn
- use SQLite under `/app/data/runtime/app.sqlite3`
- support seeding via script command
- do not copy `.venv`, caches, ignored raw report, or local DBs

Required commands documented in README:

```powershell
docker build -t ai-flowops .
docker run --rm -p 8000:8000 ai-flowops
```

Optional compose:

```powershell
docker compose up --build
```

Validation:

- Docker build succeeds.
- Container starts.
- `/healthz` returns ok.
- Seed/demo flow can run either at build-independent runtime or through documented command.

Commit: `build: add docker packaging`

## Milestone 15: CI/CD Foundation

Goal: keep main branch trustworthy.

Expand GitHub Actions.

CI jobs:

- install dependencies
- `ruff check .`
- `pytest`
- deterministic eval command
- Docker build

Triggers:

- pull requests
- push to `main`

Do not deploy anywhere yet.

Validation:

- CI passes on branch.
- Docker build runs in CI.
- Eval command runs in CI.
- README badge optional but useful.

Commit: `ci: add eval and docker checks`

## Milestone 16: Public Portfolio Polish

Goal: make the repo understandable to employers without exposing raw planning artifacts.

Update public docs:

- `README.md`
  - concise project summary
  - before/after workflow
  - screenshots placeholders or instructions
  - architecture diagram
  - demo commands
  - testing/CI commands
  - Docker commands
  - repo tour
  - AI-assisted development disclosure
- `docs/architecture.md`
  - polished architecture narrative
  - agent flow
  - HITL flow
  - eval strategy
  - security/privacy assumptions
  - v1/v2 boundary
- `docs/demo-script.md`
  - exact walkthrough for a reviewer:
    1. reset demo
    2. open dashboard
    3. inspect clean case
    4. inspect legal/security case
    5. approve or override case
    6. view trace
    7. view eval/KPI pages

Disclosure language:

- Be honest but professional:
  - “Built with AI-assisted development using ChatGPT/Codex for planning, implementation, and evaluation support.”
- Do not present the ignored raw research report publicly.
- Do not claim real customer data, real enterprise integrations, or production deployment.

Validation:

- `rg -n "AI-Business-Operations-Orchestrator||ChatGPT 5.5 deep research" README.md docs`
  - Should not find raw-report artifacts in tracked public docs.
- `git check-ignore -v docs/AI-Business-Operations-Orchestrator.md`
- `pytest`
- `ruff check .`

Commit: `docs: polish portfolio documentation`

## Final Acceptance Criteria

The build is complete only when all are true:

- `pytest` passes.
- `ruff check .` passes.
- deterministic eval runner passes thresholds.
- Docker image builds.
- GitHub Actions passes.
- App runs locally at `http://127.0.0.1:8000`.
- Dashboard supports clickable case review, approval actions, traces, KPIs, and eval results.
- 24 seed cases and 5 held-out cases validate.
- Every seed case runs end-to-end.
- Multi-agent workflow is visible in code, traces, and docs.
- Raw report remains local-only and ignored by Git.
- Public GitHub docs are clean and employer-readable.
- No secrets, private data, local DBs, venvs, caches, or raw trace dumps are committed.

Final commands before push:

```powershell
git status -sb
git check-ignore -v docs/AI-Business-Operations-Orchestrator.md
ruff check .
pytest
python scripts/demo_reset.py
python scripts/run_evals.py
docker build -t ai-flowops .
git log --oneline --decorate -5
```

Final Git steps:

```powershell
git push -u origin codex/build-ai-flowops-demo
```

Then open a pull request into `main`. Do not merge until GitHub Actions passes.

## Explicit Non-Goals For This Build

Do not build:

- real email integration
- real Slack/Jira/Linear integration
- real customer contract ingestion
- OCR/scanned PDF support
- CUAD ingestion
- role-based auth
- production VM deployment
- paid hosting deployment
- complex React/Next frontend
- autonomous unbounded agents
- hidden prompt-only routing with no deterministic policy
- tests that pass by weakening production behavior

## Assumptions

- Public product name is `AI FlowOps`.
- Repo is `ppark109/ai-flowops`.
- The first demo uses synthetic data only.
- The app uses FastAPI, Pydantic, SQLite, Pytest, Ruff, server-rendered pages, and Docker.
- The local/test default uses deterministic fallback agents.
- Real OpenAI API-capable interfaces are included but disabled unless configured.
- The strongest employer signal is an inspectable multi-agent workflow with evidence, deterministic rules, HITL approvals, traces, evals, KPIs, CI, and Docker.
