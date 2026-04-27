from __future__ import annotations

import time

from agents.base import build_trace
from schemas.case import EvidenceSpan, Finding, RoutingDecision, TraceRecord


class CriticEvaluatorAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        findings: list[Finding],
        routing_decision: RoutingDecision,
        evidence: list[EvidenceSpan],
    ) -> tuple[bool, list[str], TraceRecord]:
        start = time.perf_counter()
        findings_ids = [f.finding_id for f in findings]
        issues: list[str] = []

        if routing_decision.approval_required and not findings_ids:
            issues.append("Approval required but no findings were produced.")

        if not evidence:
            issues.append("No evidence spans available.")

        for finding in findings:
            if not finding.evidence:
                issues.append(f"Finding {finding.finding_id} missing evidence.")

        is_grounded = all(_has_real_quote(f.evidence) for f in findings)
        if not is_grounded and findings:
            issues.append("Some findings lack grounding quotes.")

        trace = build_trace(
            case_id=routing_decision.case_id,
            step_name="critic_evaluation",
            agent_name="CriticEvaluatorAgent",
            inputs_summary=f"findings={len(findings)}",
            outputs_summary=f"errors={len(issues)} grounded={is_grounded}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return (len(issues) == 0), issues, trace


def _has_real_quote(evidence: list[EvidenceSpan]) -> bool:
    return all(e.quote and len(e.quote) > 4 for e in evidence)
