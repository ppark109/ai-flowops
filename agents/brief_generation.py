from __future__ import annotations

import time

from agents.base import build_trace
from schemas.case import (
    Finding,
    GeneratedBrief,
    IntakePackage,
    RoutingDecision,
    TraceRecord,
)


class BriefGenerationAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        intake: IntakePackage,
        routing: RoutingDecision,
        findings: list[Finding],
        missing_info: list[str],
    ) -> tuple[GeneratedBrief, TraceRecord]:
        risk_summary_parts = [finding.summary for finding in findings]
        evidence_items = [f"[{f.rule_id}] {f.summary}" for f in findings if f.summary]

        recommended_next_steps = []
        if routing.approval_required:
            recommended_next_steps.append("Hold final implementation until approval is completed.")
        if not missing_info:
            recommended_next_steps.append("Create onboarding and implementation handoff tasks.")
        else:
            recommended_next_steps.append("Collect all missing intake artifacts and rerun routing.")

        brief = GeneratedBrief(
            case_id=intake.case_id,
            case_summary=intake.scenario_summary or "Synthetic commercial intake case.",
            customer_account_summary=f"{intake.customer_name} / {intake.account_name or intake.customer_name}",
            final_route=routing.recommended_route,
            risk_summary="; ".join(risk_summary_parts) or "No specific risks detected.",
            evidence_backed_findings=evidence_items,
            missing_info=missing_info,
            implementation_considerations=[f"Route workflow: {routing.recommended_route}"],
            approval_decision_summary=f"approval_required={routing.approval_required}",
            recommended_next_steps=recommended_next_steps,
        )

        trace = build_trace(
            case_id=intake.case_id,
            step_name="brief_generation",
            agent_name="BriefGenerationAgent",
            inputs_summary=f"findings={len(findings)} missing={len(missing_info)}",
            outputs_summary=f"has_next_steps={len(recommended_next_steps)}",
            start_time=time.perf_counter(),
        )
        return brief, trace
