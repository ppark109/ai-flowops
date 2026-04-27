from __future__ import annotations

import time

from agents.base import build_trace
from schemas.case import (
    Finding,
    GeneratedBrief,
    IntakePackage,
    NormalizedCase,
    RoutingDecision,
    TraceRecord,
)


class BriefGenerationAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        case: IntakePackage,
        normalized_case: NormalizedCase,
        routing_decision: RoutingDecision,
        findings: list[Finding],
        approval_summary: str | None = None,
    ) -> tuple[GeneratedBrief, TraceRecord]:
        start = time.perf_counter()
        evidence_backed_findings = [finding.summary for finding in findings]
        risk_summary = (
            "No significant risks detected."
            if not findings
            else "; ".join(finding.summary for finding in findings)
        )
        recommendations = _build_next_steps(routing_decision.recommended_route, findings)
        considerations = _build_considerations(routing_decision.recommended_route)
        approval_text = approval_summary or (
            "Approved automatically."
            if not routing_decision.approval_required
            else "Pending reviewer approval."
        )
        scenario_summary = getattr(case, "scenario_summary", case.customer_name)
        account_name = case.account_name or case.customer_name

        brief = GeneratedBrief(
            case_id=case.case_id,
            case_summary=f"{scenario_summary} / {case.customer_name}",
            customer_account_summary=f"Customer: {case.customer_name}; Account: {account_name}",
            final_route=routing_decision.recommended_route,
            risk_summary=risk_summary,
            evidence_backed_findings=evidence_backed_findings,
            missing_info=normalized_case.missing_info,
            implementation_considerations=considerations,
            approval_decision_summary=approval_text,
            recommended_next_steps=recommendations,
        )
        trace = build_trace(
            case_id=case.case_id,
            step_name="brief_generation",
            agent_name="BriefGenerationAgent",
            inputs_summary=f"findings={len(findings)} route={routing_decision.recommended_route}",
            outputs_summary=f"brief_len={len(brief.case_summary)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return brief, trace


def _build_next_steps(route: str, findings: list[Finding]) -> list[str]:
    if not findings:
        return ["Run onboarding checklist.", "Prepare implementation schedule."]
    base = {
        "legal": [
            "Complete legal review of identified clauses.",
            "Align contract language with policy.",
        ],
        "security": [
            "Collect missing security artifacts.",
            "Validate data handling and storage controls.",
        ],
        "implementation": [
            "Confirm integration plan and ownership.",
            "Resolve go-live/dependency constraints.",
        ],
        "finance": [
            "Validate commercial exception authority.",
            "Document discount/penalty/sla deviation terms.",
        ],
        "auto_approve": ["Proceed with onboarding execution."],
    }
    return base.get(route, ["Review findings and route decision."])


def _build_considerations(route: str) -> list[str]:
    return {
        "legal": ["Legal counsel review should sign off before execution."],
        "security": ["Coordinate security and compliance reviewer before go-live."],
        "implementation": ["Confirm technical owner and migration timeline."],
        "finance": ["Validate commercial exceptions with finance owner."],
        "auto_approve": ["No non-standard considerations identified."],
    }.get(route, ["Follow route-specific handoff checklist."])
