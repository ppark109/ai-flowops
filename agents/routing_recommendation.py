from __future__ import annotations

import time

from agents.base import build_trace
from schemas.case import Finding, RoutingDecision, TraceRecord
from workflows import routing


class RoutingRecommendationAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        case_id: str,
        findings: list[Finding],
        normalized_complete: bool = True,
        requested_route: str | None = None,
    ) -> tuple[RoutingDecision, TraceRecord]:
        start = time.perf_counter()

        severities = [finding.severity for finding in findings]
        route_votes = [finding.route for finding in findings]
        requested = requested_route if requested_route in routing.ESCALATION_ROUTES else None
        recommended, approval_required = routing.choose_route(
            severities,
            requested_route=requested,
            requested_route_hint=None,
            confidence=_confidence(findings),
            missing_required_info=not normalized_complete,
        )
        primary_reason = "No findings; straight-through candidate."
        triggered_rules: list[str] = [f.rule_id for f in findings]

        if findings:
            reasons = sorted(set(f.summary for f in findings))[:3]
            primary_reason = "; ".join(reasons) if reasons else primary_reason

        decision = RoutingDecision(
            case_id=case_id,
            recommended_route=recommended,
            confidence=_confidence(findings),
            approval_required=approval_required,
            reasons=[primary_reason],
            triggered_rules=triggered_rules,
            secondary_routes=[r for r in route_votes if r != recommended][:4],
        )
        trace = build_trace(
            case_id=case_id,
            step_name="routing_recommendation",
            agent_name="RoutingRecommendationAgent",
            inputs_summary=f"findings={len(findings)}",
            outputs_summary=f"route={recommended}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return decision, trace


def _confidence(findings: list[Finding]) -> float:
    if not findings:
        return 0.98
    min_conf = min((f.confidence for f in findings), default=0.8)
    # dampen confidence when multiple findings agree on escalation
    if len(findings) >= 3:
        min_conf -= 0.1
    return max(0.5, round(min_conf, 2))
