from __future__ import annotations

import time

from agents.base import build_trace, quote_from_text
from schemas.case import EvidenceSpan, IntakePackage, NormalizedCase, TraceRecord

EVIDENCE_TYPE_TO_SOURCE: dict[str, set[str]] = {
    "intake_span": {"intake_email"},
    "contract_span": {"contract"},
    "order_form_span": {"order_form"},
    "notes_span": {"implementation_notes"},
    "questionnaire_span": {"security_questionnaire"},
}


def select_evidence_for_rule(
    evidence: list[EvidenceSpan],
    *,
    rule_id: str,
    required_evidence: list[str] | tuple[str, ...] = (),
    keywords: list[str] | tuple[str, ...] = (),
    max_items: int = 2,
) -> list[EvidenceSpan]:
    """Select evidence tied to the rule by source and normalized fact text."""
    allowed_sources = {
        source
        for evidence_type in required_evidence
        for source in EVIDENCE_TYPE_TO_SOURCE.get(evidence_type, set())
    }
    search_terms = _evidence_terms(rule_id, keywords)

    source_and_term = [
        item
        for item in evidence
        if _source_matches(item, allowed_sources) and _term_matches(item, search_terms)
    ]
    term_only = [
        item
        for item in evidence
        if item not in source_and_term and _term_matches(item, search_terms)
    ]
    source_only = [
        item
        for item in evidence
        if item not in source_and_term
        and item not in term_only
        and _source_matches(item, allowed_sources)
    ]
    selected = [*source_and_term, *term_only, *source_only]
    return selected[:max_items]


def _evidence_terms(rule_id: str, keywords: list[str] | tuple[str, ...]) -> list[str]:
    raw_terms = [*keywords, rule_id.replace("playbook-", "").replace("_", " ").replace("-", " ")]
    terms: list[str] = []
    for term in raw_terms:
        normalized = term.strip().lower()
        if normalized and normalized not in terms:
            terms.append(normalized)
    return terms


def _source_matches(evidence: EvidenceSpan, allowed_sources: set[str]) -> bool:
    return not allowed_sources or evidence.source_document_type in allowed_sources


def _term_matches(evidence: EvidenceSpan, terms: list[str]) -> bool:
    haystack = f"{evidence.normalized_fact} {evidence.quote}".lower()
    return not terms or any(term in haystack for term in terms)


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
