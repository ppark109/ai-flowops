# AI FlowOps Architecture

AI FlowOps is a portfolio-grade, inspectable workflow that replaces a manual commercial
intake process with a governed AI-assisted operations pipeline.

## What changed from manual process

Manual flow:

- Email and documents were reviewed in ad hoc order.
- Legal/security/finance/implementation teams were informed piecemeal.
- No single source of truth for why cases were escalated.
- No deterministic policy boundaries, so outcomes could drift.

AI FlowOps flow:

- Intake is normalized into a standard case package.
- Specialist agents extract evidence and identify risks.
- Policy rules evaluate the case in a deterministic, auditable manner.
- Routing and approval decisions are versioned through trace logs.
- Approvals are explicit and human-owned for risky or uncertain cases.

## Multi-agent boundaries

The pipeline uses separate specialist agents with explicit boundaries:

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

Each specialist emits one or more `trace_records` and consumes/produces typed models.

## Deterministic policy layer

The playbook is data-driven (`playbooks/default.yaml`) and loaded at runtime.
It is the source of truth for route overrides and escalation behavior.

Why this matters:

- AI agents provide interpretation of text.
- The playbook provides guardrails and repeatability.
- Every escalated route can be traced to one or more rule IDs.

This is what makes the system demo-friendly for technical reviewers: risk signals are
AI-identified, but governance is policy-driven.

## Human-in-the-loop (HITL)

Cases entering with:

- high severity,
- missing required inputs,
- low confidence,
- or conflicting evidence

go through approval before finalization.

HITL actions:

- Approve
- Reject
- Override route
- Request information

Each action is persisted and represented in KPI/approval history.

## Traceability, eval, and KPIs

- **Traceability:** Every major step records model/provider, input summary, output summary,
  latency (placeholder for now), and timestamp.
- **Evals:** deterministic synthetic evals run against held-out cases with pass/fail checks
  for route, approval, grounding, and brief/task outputs.
- **KPIs:** aggregate metrics include straight-through rate, escalation rate, override rate,
  route distribution, pending approvals, and eval pass rate.

## v1 boundaries

Included in v1:

- Synthetic data only.
- No authentication layer.
- No real enterprise integrations.
- No OCR / scanned PDF parsing.
- No CUAD ingestion.

Deliberately deferred:

- External integrations (Slack, Jira, email, CRM task sync).
- Enterprise deployment and observability stack.
- Model serving and hard real-time API orchestration.
