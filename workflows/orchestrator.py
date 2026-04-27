from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    ApprovalStatus,
    Finding,
    IntakePackage,
    KPIRecord,
    NormalizedCase,
    Route,
    RoutingDecision,
    TraceRecord,
    WorkflowResult,
)
from schemas.playbook import Playbook
from workflows.playbook import match_rules
from workflows.routing import ROUTES
from workflows.storage import WorkflowStorage


class WorkflowOrchestrator:
    def __init__(self, storage: WorkflowStorage, playbook: Playbook) -> None:
        self.storage = storage
        self.playbook = playbook
        self.normalization_agent = IntakeNormalizationAgent()
        self.evidence_agent = EvidenceExtractionAgent()
        self.contract_agent = ContractRiskAgent()
        self.security_agent = SecurityReviewAgent()
        self.impl_agent = ImplementationReviewAgent()
        self.finance_agent = FinanceReviewAgent()
        self.routing_agent = RoutingRecommendationAgent()
        self.brief_agent = BriefGenerationAgent()
        self.task_agent = TaskGenerationAgent()
        self.critic = CriticEvaluatorAgent()

    def run_case(self, case: IntakePackage) -> WorkflowResult:
        normalized, norm_trace = self.normalization_agent.run(case)
        self.storage.save_normalized_case(normalized)

        evidence, evidence_trace = self.evidence_agent.run(case, normalized)
        case_traces = [norm_trace, evidence_trace]

        findings: list[Finding] = []
        contract_findings, contract_trace = self.contract_agent.run(case, normalized, evidence)
        security_findings, security_trace = self.security_agent.run(case, normalized, evidence)
        impl_findings, impl_trace = self.impl_agent.run(case, normalized, evidence)
        finance_findings, finance_trace = self.finance_agent.run(case, normalized, evidence)
        case_traces.extend([contract_trace, security_trace, impl_trace, finance_trace])

        findings.extend(contract_findings)
        findings.extend(security_findings)
        findings.extend(impl_findings)
        findings.extend(finance_findings)

        playbook_findings = match_rules(self.playbook, normalized, evidence)
        findings.extend(playbook_findings)
        self.storage.save_findings(case.case_id, findings)

        routing_decision, routing_trace = self.routing_agent.run(
            case_id=case.case_id, findings=findings, normalized_complete=normalized.package_complete
        )
        case_traces.append(routing_trace)

        grounded, critic_issues, critic_trace = self.critic.run(
            findings, routing_decision, evidence
        )
        case_traces.append(critic_trace)

        final_route = routing_decision.recommended_route
        final_requires_approval = routing_decision.approval_required or (not grounded)
        if not findings and normalized.package_complete:
            final_route, final_requires_approval = "auto_approve", False
            routing_decision.recommended_route = final_route
            routing_decision.approval_required = final_requires_approval

        if final_requires_approval:
            route_for_approval = _coerce_route(final_route)
            routing_decision.recommended_route = route_for_approval
            self.storage.save_routing_decision(case.case_id, routing_decision)
            approval = Approval(
                approval_id=f"apr-{case.case_id}",
                case_id=case.case_id,
                status="pending",
                reviewer=None,
                comments=None,
                original_route=route_for_approval,
                final_route=None,
                requested_info=(
                    "; ".join(normalized.missing_info) if normalized.missing_info else None
                ),
                created_at=datetime.now(UTC),
                resolved_at=None,
            )
            self.storage.create_approval(approval)
            brief = None
            tasks: list = []
            case_state = "awaiting_approval"
            self.storage.upsert_case(case, state=case_state)
            kpi = KPIRecord(
                case_id=case.case_id,
                final_route=route_for_approval,
                straight_through=False,
                approval_required=True,
                reviewer_override=False,
                processing_time_ms=None,
                generated_task_count=0,
            )
        else:
            approval = None
            brief, tasks, generated_traces = self._auto_generate_outputs(
                case, normalized, routing_decision, findings
            )
            case_traces.extend(generated_traces)
            self.storage.save_brief(brief)
            self.storage.save_tasks(tasks)
            case_state = "completed"
            self.storage.upsert_case(case, state=case_state)
            kpi = KPIRecord(
                case_id=case.case_id,
                final_route=final_route,
                straight_through=True,
                approval_required=False,
                reviewer_override=False,
                processing_time_ms=None,
                generated_task_count=len(tasks),
            )

        routing_decision.recommended_route = final_route
        routing_decision.approval_required = final_requires_approval
        self.storage.save_routing_decision(case.case_id, routing_decision)
        self.storage.save_kpi(kpi)
        self.storage.upsert_case(case, state=case_state)
        for trace in case_traces:
            self.storage.save_trace(trace)

        # persist and return
        self.storage.get_case_full_snapshot(case.case_id)
        return WorkflowResult(
            case_id=case.case_id,
            state=case_state,  # type: ignore[arg-type]
            case=case,
            normalized_case=normalized,
            findings=findings,
            routing_decision=routing_decision,
            approval=approval,
            brief=brief,
            tasks=tasks if not final_requires_approval else [],
            traces=case_traces,
            trace_count=len(case_traces),
            kpi=self.storage.get_kpi(case.case_id),
        )

    def run_case_by_id(self, case_id: str) -> WorkflowResult:
        case = self.storage.get_case(case_id)
        if not case:
            raise ValueError(f"Case {case_id} not found.")
        return self.run_case(case)

    def approve(
        self, approval_id: str, reviewer: str | None = None, comments: str | None = None
    ) -> WorkflowResult:
        return self._transition_approval(
            approval_id, "approved", reviewer=reviewer, comments=comments
        )

    def reject(
        self, approval_id: str, reviewer: str | None = None, comments: str | None = None
    ) -> WorkflowResult:
        return self._transition_approval(
            approval_id, "rejected", reviewer=reviewer, comments=comments
        )

    def request_info(
        self,
        approval_id: str,
        reviewer: str | None = None,
        comments: str | None = None,
        requested_info: str | None = None,
    ) -> WorkflowResult:
        return self._transition_approval(
            approval_id,
            "request_info",
            reviewer=reviewer,
            comments=comments,
            requested_info=requested_info,
        )

    def override_route(
        self,
        approval_id: str,
        route: Route,
        reviewer: str | None = None,
        comments: str | None = None,
    ) -> WorkflowResult:
        return self._transition_approval(
            approval_id,
            "override_route",
            reviewer=reviewer,
            comments=comments,
            final_route=route,
        )

    def _transition_approval(
        self,
        approval_id: str,
        new_status: ApprovalStatus,
        reviewer: str | None = None,
        comments: str | None = None,
        requested_info: str | None = None,
        final_route: Route | None = None,
    ) -> WorkflowResult:
        approval = self.storage.get_approval(approval_id)
        if not approval:
            raise ValueError("Approval not found.")

        case = self.storage.get_case(approval.case_id)
        if not case:
            raise ValueError("Case not found.")
        snapshot = self.storage.get_case_full_snapshot(case.case_id)
        if not snapshot:
            raise ValueError("Case snapshot missing.")

        final_route = final_route or approval.original_route
        patch: dict[str, Any] = {}
        if comments is not None:
            patch["comments"] = comments
        if reviewer is not None:
            patch["reviewer"] = reviewer
        if requested_info is not None:
            patch["requested_info"] = requested_info
        if final_route is not None:
            patch["final_route"] = final_route

        self.storage.update_approval_status(approval_id, status=new_status, **patch)

        if new_status == "approved":
            decision = routing_decision_from_snapshot(snapshot)
            brief, tasks, output_traces = self._auto_generate_outputs(
                case, _require_normalized(snapshot["normalized"]), decision, snapshot["findings"]
            )
            self.storage.save_brief(brief)
            self.storage.save_tasks(tasks)
            self.storage.upsert_case(case, state="completed")
            self.storage.save_kpi(
                KPIRecord(
                    case_id=case.case_id,
                    final_route=decision.recommended_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=False,
                    processing_time_ms=None,
                    generated_task_count=len(tasks),
                )
            )
            for trace in output_traces:
                self.storage.save_trace(trace)
        elif new_status == "override_route":
            decision = routing_decision_from_snapshot(snapshot, override_route=final_route)
            brief, tasks, output_traces = self._auto_generate_outputs(
                case, _require_normalized(snapshot["normalized"]), decision, snapshot["findings"]
            )
            self.storage.save_brief(brief)
            self.storage.save_tasks(tasks)
            self.storage.upsert_case(case, state="completed")
            self.storage.save_kpi(
                KPIRecord(
                    case_id=case.case_id,
                    final_route=final_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=True,
                    processing_time_ms=None,
                    generated_task_count=len(tasks),
                )
            )
            self.storage.save_routing_decision(case.case_id, decision)
            for trace in output_traces:
                self.storage.save_trace(trace)
        elif new_status == "rejected":
            self.storage.upsert_case(case, state="rejected")
            self.storage.save_kpi(
                KPIRecord(
                    case_id=case.case_id,
                    final_route=approval.original_route,
                    straight_through=False,
                    approval_required=True,
                    reviewer_override=False,
                    processing_time_ms=None,
                    generated_task_count=0,
                )
            )
        elif new_status == "request_info":
            # keep case unresolved for follow-up
            self.storage.upsert_case(case, state="awaiting_approval")

        return self._build_result_from_snapshot(case.case_id)

    def _auto_generate_outputs(
        self,
        case: IntakePackage,
        normalized_case: NormalizedCase,
        decision: RoutingDecision,
        findings: list[Finding],
    ) -> tuple[Any, list[Any], list[TraceRecord]]:
        brief, brief_trace = self.brief_agent.run(
            case=case,
            normalized_case=normalized_case,
            routing_decision=decision,
            findings=findings,
            approval_summary="Approved for automated processing."
            if decision.recommended_route == "auto_approve"
            else None,
        )
        tasks, tasks_trace = self.task_agent.run(case.case_id, decision, findings)
        return brief, tasks, [brief_trace, tasks_trace]

    def _build_result_from_snapshot(self, case_id: str) -> WorkflowResult:
        snapshot = self.storage.get_case_full_snapshot(case_id)
        if not snapshot:
            raise ValueError(f"Case {case_id} not found.")
        return WorkflowResult(
            case_id=case_id,
            state=snapshot["state"],
            case=snapshot["case"],
            normalized_case=snapshot["normalized"],
            findings=snapshot["findings"],
            routing_decision=snapshot["routing"],
            approval=snapshot["approval"],
            brief=snapshot["brief"],
            tasks=snapshot["tasks"],
            traces=snapshot["traces"],
            trace_count=len(snapshot["traces"]),
            kpi=self.storage.get_kpi(case_id),
        )


def routing_decision_from_snapshot(
    snapshot: dict[str, Any], override_route: Route | None = None
) -> RoutingDecision:
    decision = snapshot["routing"]
    if not isinstance(decision, RoutingDecision):
        decision = RoutingDecision(
            case_id=snapshot["case"].case_id,
            recommended_route="auto_approve",
            confidence=0.7,
            approval_required=True,
            reasons=["derived-from-snapshot"],
            triggered_rules=[],
            secondary_routes=[],
        )
    if override_route is not None:
        decision = RoutingDecision(
            case_id=decision.case_id,
            recommended_route=override_route,
            confidence=decision.confidence,
            approval_required=decision.approval_required,
            reasons=[f"override:{override_route}"],
            triggered_rules=decision.triggered_rules,
            secondary_routes=decision.secondary_routes,
        )
    return decision


def _require_normalized(normalized: NormalizedCase | None) -> NormalizedCase:
    if not normalized:
        raise ValueError("Case normalization payload missing.")
    return normalized


def _coerce_route(route: str) -> Route:
    return route if route in ROUTES else "auto_approve"
