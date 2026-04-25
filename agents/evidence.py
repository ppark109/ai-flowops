from __future__ import annotations

import time

from agents.base import build_trace, quote_from_text
from schemas.case import EvidenceSpan, IntakePackage, NormalizedCase, TraceRecord


def _collect_documents(payload: IntakePackage) -> list[tuple[str, str]]:
    return [
        ("intake_email", payload.intake_email_text),
        ("contract", payload.contract_text),
        ("order_form", payload.order_form_text),
        ("implementation_notes", payload.implementation_notes),
        ("security_questionnaire", payload.security_questionnaire_text),
    ]


class EvidenceExtractionAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase
    ) -> tuple[list[EvidenceSpan], list[TraceRecord]]:
        start = time.perf_counter()

        evidence: list[EvidenceSpan] = []
        risk_signals = []

        phrase_to_signal = {
            "liability cap": "liability_cap_above_standard",
            "indemnity": "nonstandard_indemnity",
            "dpa": "missing_dpa_for_regulated_data",
            "data residency": "data_residency_request",
            "regulated data": "regulated_data_without_security_artifact",
            "missing dpa": "missing_dpa_for_regulated_data",
            "aggressive": "aggressive_go_live_date",
            "next week": "aggressive_go_live_date",
            "unsupported": "unsupported_integration",
            "custom sap plugin": "unsupported_integration",
            "unclear owner": "unclear_customer_owner",
            "no owner": "unclear_customer_owner",
            "discount": "discount_above_threshold",
            "sla credits": "custom_sla_credits",
            "penalty": "unusual_penalty_terms",
            "statement of work": "missing_sow",
            "conflict": "conflicting_terms",
            "incomplete": "incomplete_intake_package",
            "critical": "regulatory_conflict",
        }

        for source, text in _collect_documents(payload):
            if not text.strip():
                continue
            low = text.lower()
            for phrase, signal in phrase_to_signal.items():
                if phrase in low:
                    if signal not in risk_signals:
                        risk_signals.append(signal)
                    evidence.append(
                        EvidenceSpan(
                            source_document_type=source,
                            locator=f"{source}:0",
                            quote=quote_from_text(text, [phrase]),
                            normalized_fact=phrase,
                            confidence=0.9,
                        )
                    )

        if not evidence:
            evidence.append(
                EvidenceSpan(
                    source_document_type="intake_email",
                    locator="intake_email_text:0",
                    quote=payload.intake_email_text[:180],
                    normalized_fact="general_intake_context",
                    confidence=0.3,
                )
            )

        normalized_case.risk_signals = list(dict.fromkeys(risk_signals))

        # Explicit rules from completion state.
        if normalized_case.missing_info:
            normalized_case.risk_signals.append("incomplete_intake_package")

        normalized_case.risk_signals = list(dict.fromkeys(normalized_case.risk_signals))

        trace = build_trace(
            case_id=payload.case_id,
            step_name="evidence_extraction",
            agent_name="EvidenceExtractionAgent",
            inputs_summary="documents=5",
            outputs_summary=f"evidence={len(evidence)} signals={len(normalized_case.risk_signals)}",
            start_time=start,
        )
        return evidence, [trace]
