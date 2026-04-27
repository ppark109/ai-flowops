from __future__ import annotations

import re
import time

from agents.base import build_trace, contains_any, quote_from_text
from schemas.case import EvidenceSpan, IntakePackage, NormalizedCase, TraceRecord

RISK_MARKERS = [
    (
        "liability_cap_above_standard",
        ["without monetary limitation", "liability cap", "unlimited liability", "no cap"],
    ),
    ("nonstandard_indemnity", ["indemnify", "indemnity", "indemnification"]),
    (
        "missing_dpa_for_regulated_data",
        [
            "does not include a signed data processing agreement",
            "dpa missing",
            "missing dpa",
            "no dpa",
        ],
    ),
    (
        "data_residency_request",
        [
            "not specified whether data residency",
            "data residency must be state-only",
            "data residency",
            "eu region",
            "region-specific",
            "geo-fenced",
        ],
    ),
    ("regulated_data_without_security_artifact", ["phi", "pii", "regulated", "sensitive data"]),
    ("aggressive_go_live_date", ["go-live", "go live", "next week", "3 days", "urgent launch"]),
    (
        "unsupported_integration",
        [
            "legacy mainframe eligibility and payment systems",
            "legacy mainframe",
            "unsupported",
            "custom integration",
            "mainframe connector",
        ],
    ),
    (
        "unclear_customer_owner",
        ["unclear owner", "owner not assigned", "ownership TBD", "owner TBD"],
    ),
    ("dependency_conflict", ["dependency conflict", "tooling conflict", "migration conflict"]),
    (
        "fixed_fee_scope_risk",
        ["fixed fee of $4,800,000", "fixed-fee implementation", "fixed fee includes"],
    ),
    ("discount_above_threshold", ["discount", "50%", "45%", "60%", "40%"]),
    ("custom_sla_credits", ["sla credits", "service credits", "credit"]),
    ("unusual_penalty_terms", ["penalty", "penalties", "refund", "termination fee"]),
    ("missing_sow", ["statement of work", "sow", "missing statement"]),
    ("conflicting_terms", ["conflicting terms", "contract conflict", "contradictory terms"]),
    (
        "implementation_dependency_risk",
        ["agency dependencies", "department dependency", "test data availability"],
    ),
]

SOURCE_PREFERENCES = {
    "liability_cap_above_standard": ["contract"],
    "nonstandard_indemnity": ["contract"],
    "missing_dpa_for_regulated_data": ["security_questionnaire", "contract"],
    "data_residency_request": ["security_questionnaire", "contract"],
    "regulated_data_without_security_artifact": ["security_questionnaire"],
    "aggressive_go_live_date": ["implementation", "contract"],
    "unsupported_integration": ["implementation", "contract"],
    "unclear_customer_owner": ["implementation"],
    "dependency_conflict": ["implementation", "order_form"],
    "fixed_fee_scope_risk": ["order_form", "contract"],
    "discount_above_threshold": ["order_form"],
    "custom_sla_credits": ["order_form", "contract"],
    "unusual_penalty_terms": ["order_form", "contract"],
    "missing_sow": ["implementation", "intake"],
    "conflicting_terms": ["contract", "implementation", "order_form"],
    "implementation_dependency_risk": ["implementation", "order_form"],
}


class EvidenceExtractionAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, payload: IntakePackage, normalized_case: NormalizedCase
    ) -> tuple[list[EvidenceSpan], TraceRecord]:
        start = time.perf_counter()

        field_map = {
            "intake_email_text": ("intake", payload.intake_email_text),
            "contract_text": ("contract", payload.contract_text),
            "order_form_text": ("order_form", payload.order_form_text),
            "implementation_notes": ("implementation", payload.implementation_notes),
            "security_questionnaire_text": (
                "security_questionnaire",
                payload.security_questionnaire_text,
            ),
        }

        evidence: list[EvidenceSpan] = []
        detected: set[str] = set()
        for label, phrases in RISK_MARKERS:
            for source, text in _ordered_fields(field_map, SOURCE_PREFERENCES.get(label, [])):
                if contains_any(text, phrases):
                    detected.add(label)
                    evidence.append(
                        EvidenceSpan(
                            source_document_type=source,
                            locator=f"{source}:0",
                            quote=quote_from_text(text, phrases),
                            normalized_fact=label,
                            confidence=0.9,
                        )
                    )
                    break

        normalized_case.risk_signals = sorted(detected)
        if not evidence:
            evidence.append(
                EvidenceSpan(
                    source_document_type="intake",
                    locator="intake:0",
                    quote=payload.intake_email_text[:140],
                    normalized_fact="no_specialized_risk_signal",
                    confidence=0.3,
                )
            )

        # add a low confidence hint for discount percentages in order form
        discount = _extract_percent(payload.order_form_text)
        if discount and discount > 35:
            normalized_case.risk_signals.append("discount_above_threshold")
            evidence.append(
                EvidenceSpan(
                    source_document_type="order_form",
                    locator="order_form:0",
                    quote=quote_from_text(payload.order_form_text, [f"{discount}%"]),
                    normalized_fact=f"discount_{int(discount)}_pct",
                    confidence=0.95,
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="evidence_extraction",
            agent_name="EvidenceExtractionAgent",
            inputs_summary=f"documents={len(field_map)}",
            outputs_summary=f"evidence={len(evidence)} signals={len(normalized_case.risk_signals)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return evidence, trace


def _extract_percent(text: str) -> float | None:
    match = re.search(r"(\d{2,3})\s*%", text.lower())
    if not match:
        return None
    return float(match.group(1))


def _ordered_fields(
    field_map: dict[str, tuple[str, str]], preferred_sources: list[str]
) -> list[tuple[str, str]]:
    fields = list(field_map.values())
    if not preferred_sources:
        return fields
    preferred = [
        field
        for source in preferred_sources
        for field in fields
        if field[0] == source
    ]
    remainder = [field for field in fields if field[0] not in preferred_sources]
    return preferred + remainder
