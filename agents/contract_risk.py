from __future__ import annotations

import time

from agents.base import build_trace, evidence_for_rule, next_finding_id
from schemas.case import Finding, IntakePackage, NormalizedCase, TraceRecord


class ContractRiskAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase, evidence: list
    ) -> tuple[list[Finding], TraceRecord]:
        start = time.perf_counter()
        findings: list[Finding] = []
        low_text = (
            f"{payload.contract_text} {payload.intake_email_text} "
            f"{payload.order_form_text} {payload.implementation_notes}".lower()
        )

        def has(phrase: str) -> bool:
            return phrase in low_text

        if has("liability cap") or has("no liability cap") or has("unlimited liability"):
            findings.append(
                _finding(
                    case_id=payload.case_id,
                    label="liability_cap_above_standard",
                    route="legal",
                    severity="high"
                    if ("unlimited" in low_text or "above" in low_text)
                    else "medium",
                    summary="Liability cap appears nonstandard.",
                    evidence=evidence,
                )
            )

        if has("indemnity") and "standard" not in low_text:
            findings.append(
                _finding(
                    case_id=payload.case_id,
                    label="nonstandard_indemnity",
                    route="legal",
                    severity="high",
                    summary="Indemnity language appears nonstandard.",
                    evidence=evidence,
                )
            )

        if has("conflicting terms") or has("contract conflict") or has("contradictory terms"):
            findings.append(
                _finding(
                    case_id=payload.case_id,
                    label="conflicting_terms",
                    route="legal",
                    severity="high",
                    summary="Contract contains contradictory terms.",
                    evidence=evidence,
                )
            )

        if (
            has("immediate termination")
            or has("non-standard termination")
            or has("unusual termination")
        ):
            findings.append(
                _finding(
                    case_id=payload.case_id,
                    label="termination_terms",
                    route="legal",
                    severity="medium",
                    summary="Termination language needs policy review.",
                    evidence=evidence,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="contract_risk_review",
            agent_name="ContractRiskAgent",
            inputs_summary=f"normalized_requirements={len(normalized_case.extracted_requirements)}",
            outputs_summary=f"findings={len(findings)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return findings, trace


def _finding(
    case_id: str,
    label: str,
    route: str,
    severity: str,
    summary: str,
    evidence: list,
) -> Finding:
    from schemas.case import EvidenceSpan

    source_evidence = evidence_for_rule(evidence, label)
    if not source_evidence:
        source_evidence = [
            EvidenceSpan(
                source_document_type="contract",
                locator="contract:0",
                quote="auto-generated synthetic text",
                normalized_fact=label,
                confidence=0.6,
            )
        ]
    return Finding(
        finding_id=next_finding_id("legal"),
        rule_id=label,
        finding_type="contract_risk",
        severity=severity,  # type: ignore[arg-type]
        route=route,  # type: ignore[arg-type]
        summary=summary,
        evidence=source_evidence,
        confidence=0.9,
    )
