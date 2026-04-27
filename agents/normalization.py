from __future__ import annotations

import time

from agents.base import build_trace, contains_any, hash_text, next_finding_id
from schemas.case import DocumentRef, IntakePackage, NormalizedCase, TraceRecord

REQUIRED_SECTIONS = [
    "intake_email_text",
    "contract_text",
    "order_form_text",
    "implementation_notes",
    "security_questionnaire_text",
]


class IntakeNormalizationAgent:
    provider_label = "deterministic-fallback"

    def run(self, payload: IntakePackage) -> tuple[NormalizedCase, TraceRecord]:
        start = time.perf_counter()

        missing = []
        for field in REQUIRED_SECTIONS:
            value = getattr(payload, field)
            cleaned = (value or "").strip().lower()
            if not value or cleaned in {"todo", "na", "n/a", "lorem", "example.com"}:
                missing.append(field)

        requirements = []
        for value in [
            payload.intake_email_text,
            payload.contract_text,
            payload.order_form_text,
            payload.implementation_notes,
            payload.security_questionnaire_text,
        ]:
            requirements.extend(
                [
                    segment.strip()
                    for segment in value.replace(";", "\n").split("\n")
                    if segment.strip()
                ]
            )

        docs = [
            DocumentRef(
                document_id=f"doc-{next_finding_id('doc')[:8]}",
                document_type="intake_email",
                source_name="intake_email_text",
                content_hash=hash_text(payload.intake_email_text),
            ),
            DocumentRef(
                document_id=f"doc-{next_finding_id('doc')[:8]}",
                document_type="contract",
                source_name="contract_text",
                content_hash=hash_text(payload.contract_text),
            ),
            DocumentRef(
                document_id=f"doc-{next_finding_id('doc')[:8]}",
                document_type="order_form",
                source_name="order_form_text",
                content_hash=hash_text(payload.order_form_text),
            ),
            DocumentRef(
                document_id=f"doc-{next_finding_id('doc')[:8]}",
                document_type="implementation_notes",
                source_name="implementation_notes",
                content_hash=hash_text(payload.implementation_notes),
            ),
            DocumentRef(
                document_id=f"doc-{next_finding_id('doc')[:8]}",
                document_type="security_questionnaire",
                source_name="security_questionnaire_text",
                content_hash=hash_text(payload.security_questionnaire_text),
            ),
        ]

        normalized = NormalizedCase(
            case_id=payload.case_id,
            customer_name=payload.customer_name,
            normalized_account_info={
                "customer_name": payload.customer_name,
                "account_name": payload.account_name or payload.customer_name,
            },
            document_refs=docs,
            extracted_requirements=[r for r in requirements[:12] if len(r) > 5],
            missing_info=missing,
            package_complete=not missing,
            risk_signals=[],
            metadata={
                "contains_clean_marker": contains_any(
                    payload.intake_email_text, ["standard", "complete", "ready"]
                ),
            },
        )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="intake_normalization",
            agent_name="IntakeNormalizationAgent",
            inputs_summary=f"required_fields={len(REQUIRED_SECTIONS)}",
            outputs_summary=(
                f"requirements={len(normalized.extracted_requirements)} "
                f"package_complete={normalized.package_complete}"
            ),
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return normalized, trace
