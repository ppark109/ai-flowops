# AI FlowOps Architecture

## Purpose

`AI FlowOps` demonstrates how a manual commercial intake process can be converted into a governed AI operations workflow.  
The core question for the demo is: **Can AI help structure decisions while remaining auditable, deterministic, and easy for a reviewer to inspect?**

## Before AI FlowOps (Manual Flow)

- Intake arrives as multiple text blocks and spreadsheets.
- Intake reviewers manually inspect contracts, questionnaires, and order terms.
- Routing and escalation decisions are ad hoc and inconsistent.
- Cases move slowly into spreadsheets, email threads, and task tools.
- Evidence, decision rationale, and completion metrics are difficult to audit.
- Approval exceptions are difficult to distinguish from normal routing noise.

## After AI FlowOps (Governed AI Flow)

1. A case enters as a standardized intake package.
2. Specialist modules normalize the package and extract evidence-backed facts.
3. Rule-based policy and specialist findings are applied deterministically.
4. A routing decision is produced with confidence and approval requirements.
5. A critic/evaluator validates minimum quality constraints.
6. Safe cases generate briefs and tasks automatically.
7. Risky/uncertain cases pause for explicit human approval.
8. Approvals, traces, evals, and KPIs are stored for auditability.

## Multi-Agent Layout

- **Intake Normalization Agent**  
  Normalizes incoming fields into a consistent structure and identifies missing inputs.

- **Evidence Extraction Agent**  
  Pulls quoted snippets from source text and publishes normalized facts.

- **Contract Risk Agent**
- **Security Review Agent**
- **Implementation Review Agent**
- **Finance Review Agent**  
  These specialists output findings tied to the route, severity, and evidence.

- **Routing Recommendation Agent**  
  Produces an initial route and confidence from findings.

- **Brief Generation Agent**
- **Task Generation Agent**
- **Critic/Evaluator Agent**  
  Produces operational handoff outputs and guardrail checks.

## Why Deterministic Playbook Routing

In this version, policy is explicit and inspectable in YAML. The playbook:

- Makes routing deterministic for a given input.
- Prevents hidden prompt-only decisions.
- Creates a clear path to proving why a case was escalated.
- Enables stable regression tests against synthetic fixtures.

This is intentionally conservative for a portfolio demo. It shows governance-first AI design instead of "just prompt magic."

## HITL Behavior

- High risk, low confidence, conflicting findings, or missing required package inputs create pending approvals.
- Human reviewers can:
  - approve,
  - reject,
  - override route,
  - request additional information.
- Approval records capture reviewer, action, comments, and final routing outcome.
- Approved/reviewed cases keep generated artifacts; rejected and request-info cases do not produce final implementation tasks.

## Trace / Eval / KPI

- **Trace**: each major step writes a timestamped trace record with step name, module, and input/output summary.
- **Eval**: held-out and deterministic seed evals verify route, approval, grounding, brief completeness, and trace completeness.
- **KPI**: aggregate metrics report throughput style outcomes such as straight-through rate, escalation, override, and route distribution.

## MVP Boundaries (v1)

- Synthetic data only.
- No auth and no role-based access.
- No OCR or scanned document pipeline.
- No CUAD ingestion.
- No production email/PM-system integrations.

## v1 vs Future

- **v1 (current)**: deterministic multi-agent workflow, local SQLite persistence, server-rendered review UI, CI, Docker.
- **v2 (future)**: optional model routing providers, queue workers, ticketing integrations, tenant-level auth, richer monitoring.
