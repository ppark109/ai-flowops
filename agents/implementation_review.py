from __future__ import annotations

import time

from agents.base import build_trace, evidence_for_rule, next_finding_id
from schemas.case import Finding, IntakePackage, NormalizedCase, TraceRecord


class ImplementationReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase, evidence: list
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        findings: list[Finding] = []
        text = " ".join(
            [
                payload.implementation_notes,
                payload.order_form_text,
                payload.intake_email_text,
            ]
        ).lower()

        if "next week" in text or "3 days" in text or "aggressive" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "aggressive_go_live_date",
                    "implementation",
                    "medium",
                    "Implementation timeline is aggressive.",
                    evidence,
                )
            )

        if "legacy" in text or "unsupported" in text or "custom" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "unsupported_integration",
                    "implementation",
                    "medium",
                    "Requested integration is unusual or unsupported.",
                    evidence,
                )
            )

        if (
            "unclear owner" in text
            or "owner not assigned" in text
            or "ownership tbd" in text
        ):
            findings.append(
                _finding(
                    payload.case_id,
                    "unclear_customer_owner",
                    "implementation",
                    "medium",
                    "Customer owner/decision authority is unclear.",
                    evidence,
                )
            )

        if (
            "agency dependencies" in text
            or "department dependency" in text
            or "test data availability" in text
        ):
            findings.append(
                _finding(
                    payload.case_id,
                    "implementation_dependency_risk",
                    "implementation",
                    "medium",
                    "Implementation depends on agency access, test data, and decision makers.",
                    evidence,
                )
            )

        if "conflict" in text and ("dependency" in text or "tooling" in text):
            findings.append(
                _finding(
                    payload.case_id,
                    "dependency_conflict",
                    "implementation",
                    "medium",
                    "Dependency conflict flagged in implementation notes.",
                    evidence,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="implementation_review",
            agent_name="ImplementationReviewAgent",
            inputs_summary=f"risk_signals={len(normalized_case.risk_signals)}",
            outputs_summary=f"findings={len(findings)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return findings, trace


def _finding(
    case_id: str, rule_id: str, route: str, severity: str, summary: str, evidence: list
) -> Finding:
    from schemas.case import EvidenceSpan

    source_evidence = evidence_for_rule(evidence, rule_id)
    if not source_evidence:
        source_evidence = [
            EvidenceSpan(
                source_document_type="implementation",
                locator="implementation:0",
                quote="implementation scope text",
                normalized_fact=rule_id,
                confidence=0.6,
            )
        ]
    return Finding(
        finding_id=next_finding_id("impl"),
        rule_id=rule_id,
        finding_type="implementation_review",
        severity=severity,  # type: ignore[arg-type]
        route=route,  # type: ignore[arg-type]
        summary=summary,
        evidence=source_evidence,
        confidence=0.9,
    )
