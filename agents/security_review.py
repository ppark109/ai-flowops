from __future__ import annotations

import time

from agents.base import build_trace, evidence_for_rule, next_finding_id
from schemas.case import Finding, IntakePackage, NormalizedCase, TraceRecord


class SecurityReviewAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase, evidence: list
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        findings: list[Finding] = []
        text = " ".join(
            [
                payload.contract_text,
                payload.security_questionnaire_text,
                payload.order_form_text,
                payload.implementation_notes,
            ]
        ).lower()

        if ("dpa" in text and "missing" in text) or (
            "does not include a signed data processing agreement" in text
        ):
            findings.append(
                _finding(
                    payload.case_id,
                    "missing_dpa_for_regulated_data",
                    "security",
                    "high",
                    "DPA is explicitly missing for regulated scope.",
                    evidence,
                )
            )

        if "data residency" in text or "residency" in text or "eu" in text:
            findings.append(
                _finding(
                    payload.case_id,
                    "data_residency_request",
                    "security",
                    "high",
                    "Customer asks for residency control not yet approved.",
                    evidence,
                )
            )

        if ("phi" in text or "pci" in text or "pii" in text) and (
            "artifact" not in text and "controls" not in text
        ):
            findings.append(
                _finding(
                    payload.case_id,
                    "regulated_data_without_security_artifact",
                    "security",
                    "medium",
                    "Regulated data processing lacks supporting artifacts.",
                    evidence,
                )
            )

        if (
            "incomplete security questionnaire" in text
            or "security questionnaire is incomplete" in text
            or "missing security questionnaire" in text
        ):
            findings.append(
                _finding(
                    payload.case_id,
                    "missing_security_artifacts",
                    "security",
                    "medium",
                    "Security questionnaire appears incomplete.",
                    evidence,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="security_review",
            agent_name="SecurityReviewAgent",
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
                source_document_type="security_questionnaire",
                locator="security_questionnaire:0",
                quote="security scope text",
                normalized_fact=rule_id,
                confidence=0.6,
            )
        ]
    return Finding(
        finding_id=next_finding_id("security"),
        rule_id=rule_id,
        finding_type="security_review",
        severity=severity,  # type: ignore[arg-type]
        route=route,  # type: ignore[arg-type]
        summary=summary,
        evidence=source_evidence,
        confidence=0.9,
    )
