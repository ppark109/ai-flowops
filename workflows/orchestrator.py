from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from agents import (
    BriefGenerationAgent,
    ContractRiskAgent,
    CriticEvaluatorAgent,
    EvidenceExtractionAgent,
    FinanceReviewAgent,
    ImplementationReviewAgent,
    IntakeNormalizationAgent,
    RoutingRecommendationAgent,
    SecurityReviewAgent,
    TaskGenerationAgent,
)
from schemas.case import (
    Approval,
    CaseWorkflowState,
    EvidenceSpan,
    Finding,
    GeneratedBrief,
    GeneratedTask,
    IntakePackage,
    KPIRecord,
    NormalizedCase,
    Route,
    RoutingDecision,
    RoutingResult,
    TraceRecord,
    WorkflowRunResult,
)
from workflows.playbook import load_default_playbook, match_rules
from workflows.routing import choose_route
from workflows.seeding import seed_cases
from workflows.storage import WorkflowStore


def _default_db_path() -> Path:
    return Path("data/runtime/app.sqlite3")


class WorkflowOrchestrator:
    """End-to-end orchestrator for the v1 deterministic workflow."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.store = WorkflowStore(db_path or _default_db_path())
        self.playbook = load_default_playbook()
        self.normalization_agent = IntakeNormalizationAgent()
        self.evidence_agent = EvidenceExtractionAgent()
        self.contract_agent = ContractRiskAgent()
        self.security_agent = SecurityReviewAgent()
        self.implementation_agent = ImplementationReviewAgent()
        self.finance_agent = FinanceReviewAgent()
        self.router = RoutingRecommendationAgent()
        self.brief_agent = BriefGenerationAgent()
        self.task_agent = TaskGenerationAgent()
        self.critic = CriticEvaluatorAgent()

    def close(self) -> None:
        self.store.close()

    def list_cases(self) -> list[dict[str, object]]:
        return self.store.list_cases()

    def list_approvals(self) -> list[Approval]:
        return self.store.list_pending_approvals()

    def create_case(self, intake: IntakePackage) -> str:
        self.store.upsert_case(intake, status="draft")
        return intake.case_id

    def seed(self, folder: Path | str, *, overwrite: bool = False) -> dict[str, int]:
        return seed_cases(self.store, folder, overwrite=overwrite)

    def run_case(self, case_id: str, requested_route: Route | None = None) -> WorkflowRunResult:
        intake = self.store.get_intake(case_id)
        traces: list[TraceRecord] = []

        normalized_result = self.normalization_agent.run(intake)
        normalized = normalized_result.normalized_case
        traces.append(normalized_result.trace)

        evidence, evidence_trace = self.evidence_agent.run(intake, normalized)
        traces.extend(evidence_trace)

        contract_findings, contract_trace = self.contract_agent.run(intake, normalized, evidence)
        security_findings, security_trace = self.security_agent.run(intake, normalized, evidence)
        impl_findings, impl_trace = self.implementation_agent.run(intake, normalized, evidence)
        finance_findings, finance_trace = self.finance_agent.run(intake, normalized, evidence)
        traces.extend([contract_trace, security_trace, impl_trace, finance_trace])

        specialist_findings = _dedupe_findings(
            [*contract_findings, *security_findings, *impl_findings, *finance_findings]
        )
        playbook_findings = _dedupe_findings(match_rules(self.playbook, normalized, evidence))

        all_findings = _dedupe_findings([*specialist_findings, *playbook_findings])

        recommendation = self.router.run(all_findings)
        traces.append(
            TraceRecord(
                case_id=case_id,
                step_name="routing_recommendation",
                agent_name="RoutingRecommendationAgent",
                model_provider_label="deterministic-fallback",
                inputs_summary=f"findings={len(all_findings)}",
                outputs_summary=f"route={recommendation.recommended_route}",
                latency_ms=0,
            )
        )

        final_route, approval_required, secondary_routes = choose_route(
            findings=all_findings,
            confidence=recommendation.confidence,
            missing_required_info=bool(normalized.missing_info),
            requested_route=requested_route,
            has_conflicting_evidence=has_conflicting_findings(all_findings),
        )

        critic_issues = self.critic.run(intake, normalized, evidence, all_findings)
        routing = RoutingDecision(
            recommended_route=final_route,
            confidence=max(0.71, recommendation.confidence),
            approval_required=approval_required or bool(critic_issues),
            reasons=sorted(set(recommendation.reasons + critic_issues)),
            triggered_rules=sorted(set(recommendation.triggered_rules)),
            secondary_routes=sorted(set(secondary_routes)),
        )

        if routing.approval_required:
            routing.reasons = _ensure_reason_if_missing(routing.reasons, "requires_approval")

        self.store.set_status(
            case_id, "pending_approval" if routing.approval_required else "completed"
        )
        self.store.save_normalized_case(case_id, normalized)
        self.store.save_findings(case_id, all_findings)
        self.store.save_routing_decision(case_id, routing)

        traces.append(
            TraceRecord(
                case_id=case_id,
                step_name="playbook_and_routing",
                agent_name="WorkflowOrchestrator",
                model_provider_label="deterministic-fallback",
                inputs_summary=(
                    f"specialist={len(specialist_findings)} "
                    f"playbook={len(playbook_findings)}"
                ),
                outputs_summary=(
                    f"route={routing.recommended_route} "
                    f"approval_required={routing.approval_required}"
                ),
                latency_ms=0,
            )
        )
        traces.append(
            TraceRecord(
                case_id=case_id,
                step_name="critic",
                agent_name="CriticEvaluatorAgent",
                model_provider_label="deterministic-fallback",
                inputs_summary=f"findings={len(all_findings)} evidence={len(evidence)}",
                outputs_summary=f"issues={len(critic_issues)}",
                latency_ms=0,
            )
        )

        if routing.approval_required:
            existing = self.store.get_approval(case_id)
            if existing and existing.status in {"approved", "override_route"}:
                review_state = existing
            else:
                review_state = (
                    existing.model_copy(update={"case_id": case_id}) if existing else None
                )

            approval = review_state or Approval(
                approval_id=f"apr-{uuid4().hex[:8]}",
                case_id=case_id,
                status="pending",
                reviewer=None,
                comments=None,
                original_route=routing.recommended_route,
                final_route=routing.recommended_route,
            )
            if approval.status != "pending":
                approval = approval.model_copy(update={"status": "pending", "resolved_at": None})
            self.store.save_approval(case_id, approval)
            self.store.save_traces(traces)
            self.store.save_kpi(
                KPIRecord(
                    case_id=case_id,
                    final_route=routing.recommended_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=False,
                    processing_time_ms=None,
                    generated_task_count=0,
                )
            )

            return WorkflowRunResult(
                case_id=case_id,
                status="pending_approval",
                state="pending_approval",
                routing=RoutingResult(
                    final_route=routing.recommended_route,
                    confidence=routing.confidence,
                    approval_required=True,
                    reasons=routing.reasons,
                    triggered_rules=routing.triggered_rules,
                    secondary_routes=routing.secondary_routes,
                ),
                straight_through=False,
                approval_id=approval.approval_id,
                has_brief=False,
                task_count=0,
            )

        brief, task_items, output_traces = _generate_outputs(
            intake,
            normalized,
            routing,
            all_findings,
            self.brief_agent,
            self.task_agent,
        )
        traces.extend(output_traces)
        self.store.save_brief(case_id, brief)
        self.store.save_tasks(case_id, task_items)
        self.store.save_traces(traces)
        self.store.save_kpi(
            KPIRecord(
                case_id=case_id,
                final_route=routing.recommended_route,
                straight_through=True,
                approval_required=False,
                reviewer_override=False,
                processing_time_ms=None,
                generated_task_count=len(task_items),
            )
        )

        return WorkflowRunResult(
            case_id=case_id,
            status="completed",
            state="completed",
            routing=RoutingResult(
                final_route=routing.recommended_route,
                confidence=routing.confidence,
                approval_required=False,
                reasons=routing.reasons,
                triggered_rules=routing.triggered_rules,
                secondary_routes=routing.secondary_routes,
            ),
            straight_through=True,
            approval_id=None,
            has_brief=True,
            task_count=len(task_items),
        )

    def apply_approval(
        self,
        approval_id: str,
        action: Literal["approve", "reject", "override_route", "request_info"],
        *,
        reviewer: str | None = None,
        comments: str | None = None,
        override_route: Route | None = None,
        request_info: str | None = None,
    ) -> CaseWorkflowState:
        approval = self.store.get_approval_by_id(approval_id)
        if approval is None:
            raise KeyError(approval_id)

        case_id = approval.case_id
        routing = self.store.get_routing_decision(case_id)
        if routing is None:
            raise ValueError(f"Missing routing decision for case {case_id}")

        state = self.store.get_case_state(case_id)
        normalized = state.normalized_case
        findings = state.findings
        # trace evidence collection is preserved inside specialist agents and is
        # intentionally not used directly in this approval path.

        if action == "approve":
            routing = routing.model_copy(update={"approval_required": False})
            brief, task_items, output_traces = _generate_outputs(
                state.intake,
                normalized,
                routing,
                findings,
                self.brief_agent,
                self.task_agent,
            )
            self.store.save_brief(case_id, brief)
            self.store.save_tasks(case_id, task_items)
            self.store.save_approval(
                case_id,
                approval.model_copy(
                    update={
                        "status": "approved",
                        "comments": comments,
                        "reviewer": reviewer,
                        "resolved_at": datetime.now(UTC),
                        "final_route": routing.recommended_route,
                    }
                ),
            )
            self.store.set_status(case_id, "approved")
            self.store.save_kpi(
                KPIRecord(
                    case_id=case_id,
                    final_route=routing.recommended_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=False,
                    processing_time_ms=None,
                    generated_task_count=len(task_items),
                )
            )
            self.store.save_traces(
                output_traces
                + [
                    TraceRecord(
                        case_id=case_id,
                        step_name="approval_action",
                        agent_name="WorkflowOrchestrator",
                        model_provider_label="manual",
                        inputs_summary=f"action={action}",
                        outputs_summary="brief_and_tasks_generated",
                    )
                ]
            )
            return self.store.get_case_state(case_id)

        if action == "reject":
            self.store.save_approval(
                case_id,
                approval.model_copy(
                    update={
                        "status": "rejected",
                        "comments": comments,
                        "reviewer": reviewer or "",
                        "resolved_at": datetime.now(UTC),
                    }
                ),
            )
            self.store.set_status(case_id, "rejected")
            self.store.save_traces(
                [
                    TraceRecord(
                        case_id=case_id,
                        step_name="approval_action",
                        agent_name="WorkflowOrchestrator",
                        model_provider_label="manual",
                        inputs_summary=f"action={action}",
                        outputs_summary="rejected",
                    )
                ]
            )
            return self.store.get_case_state(case_id)

        if action == "override_route":
            if override_route is None:
                raise ValueError("override_route required")
            if not comments:
                raise ValueError("comments required for override")
            revised = routing.model_copy(
                update={"recommended_route": override_route, "approval_required": False}
            )
            self.store.save_routing_decision(case_id, revised)
            brief, task_items, output_traces = _generate_outputs(
                state.intake,
                normalized,
                revised,
                findings,
                self.brief_agent,
                self.task_agent,
            )
            self.store.save_brief(case_id, brief)
            self.store.save_tasks(case_id, task_items)
            self.store.save_approval(
                case_id,
                approval.model_copy(
                    update={
                        "status": "override_route",
                        "comments": comments,
                        "reviewer": reviewer or "",
                        "final_route": override_route,
                        "resolved_at": datetime.now(UTC),
                    }
                ),
            )
            self.store.set_status(case_id, "approved")
            self.store.save_kpi(
                KPIRecord(
                    case_id=case_id,
                    final_route=override_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=True,
                    processing_time_ms=None,
                    generated_task_count=len(task_items),
                )
            )
            self.store.save_traces(
                output_traces
                + [
                    TraceRecord(
                        case_id=case_id,
                        step_name="approval_action",
                        agent_name="WorkflowOrchestrator",
                        model_provider_label="manual",
                        inputs_summary=f"action={action}",
                        outputs_summary=f"overridden_route={override_route}",
                    )
                ]
            )
            return self.store.get_case_state(case_id)

        if action == "request_info":
            if not request_info and not comments:
                raise ValueError("request_info text required")
            self.store.save_approval(
                case_id,
                approval.model_copy(
                    update={
                        "status": "request_info",
                        "comments": request_info or comments,
                        "reviewer": reviewer,
                        "resolved_at": None,
                        "requested_info": request_info or comments,
                    }
                ),
            )
            self.store.set_status(case_id, "pending_approval")
            self.store.save_traces(
                [
                    TraceRecord(
                        case_id=case_id,
                        step_name="approval_action",
                        agent_name="WorkflowOrchestrator",
                        model_provider_label="manual",
                        inputs_summary=f"action={action}",
                        outputs_summary="requested_missing_info",
                    )
                ]
            )
            return self.store.get_case_state(case_id)

        raise ValueError(f"Unknown action: {action}")


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    unique: dict[str, Finding] = {}
    for finding in findings:
        if finding.finding_id and finding.finding_id not in unique:
            unique[finding.finding_id] = finding
    return list(unique.values())


def _ensure_reason_if_missing(reasons: list[str], required: str) -> list[str]:
    if required not in reasons:
        reasons.append(required)
    return reasons


def has_conflicting_findings(findings: list[Finding]) -> bool:
    return any("conflict" in finding.summary.lower() for finding in findings)


def _generate_outputs(
    intake: IntakePackage,
    normalized: NormalizedCase,
    routing: RoutingDecision,
    findings: list[Finding],
    brief_agent: BriefGenerationAgent,
    task_agent: TaskGenerationAgent,
) -> tuple[GeneratedBrief, list[GeneratedTask], list[TraceRecord]]:
    brief, brief_trace = brief_agent.run(
        intake,
        routing,
        findings,
        normalized.missing_info,
    )
    tasks, task_trace = task_agent.run(intake, routing, findings)
    return brief, tasks, [brief_trace, task_trace]


def _collect_evidence_for_case(findings: list[Finding]) -> list[EvidenceSpan]:
    evidence: list[EvidenceSpan] = []
    for finding in findings:
        evidence.extend(finding.evidence)
    return evidence
