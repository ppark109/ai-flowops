from __future__ import annotations

from schemas.case import Finding, RoutingDecision


class RoutingRecommendationAgent:
    provider_label = "deterministic-fallback"

    def run(self, findings: list[Finding]) -> RoutingDecision:
        if not findings:
            return RoutingDecision(
                recommended_route="auto_approve",
                confidence=0.95,
                approval_required=False,
                reasons=[],
                triggered_rules=[],
                secondary_routes=[],
            )

        sorted_findings = sorted(
            findings,
            key=lambda item: (item.severity, item.route),
            reverse=True,
        )
        top = sorted_findings[0]

        reasons = [finding.summary for finding in sorted_findings]
        triggered = [finding.rule_id for finding in sorted_findings]
        secondary = []
        for finding in sorted_findings[1:]:
            if finding.route != top.route and finding.route not in secondary:
                secondary.append(finding.route)

        confidence = min(0.96, 0.7 + 0.15 * len(findings))
        if top.severity in {"high", "critical"}:
            confidence = max(0.95, confidence)

        approval_required = False if top.route == "auto_approve" else True
        if top.route == "auto_approve" and any(
            f.severity in {"high", "critical"} for f in findings
        ):
            approval_required = True

        return RoutingDecision(
            recommended_route=top.route,
            confidence=confidence,
            approval_required=approval_required,
            reasons=reasons,
            triggered_rules=triggered,
            secondary_routes=secondary,
        )
