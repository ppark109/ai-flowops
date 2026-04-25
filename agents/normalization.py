from __future__ import annotations

import time
from dataclasses import dataclass

from agents.base import build_trace, contains_any
from schemas.case import DocumentRef, IntakePackage, NormalizedCase, TraceRecord


@dataclass
class NormalizationResult:
    normalized_case: NormalizedCase
    trace: TraceRecord


class IntakeNormalizationAgent:
    provider_label = "deterministic-fallback"

    def run(self, payload: IntakePackage) -> NormalizationResult:
        start = time.perf_counter()

        placeholders = {"todo", "lorem", "example.com", "n/a", "na", ""}
        missing = []
        for field_name in [
            "intake_email_text",
            "contract_text",
            "order_form_text",
            "implementation_notes",
            "security_questionnaire_text",
        ]:
            value = getattr(payload, field_name)
            compact = value.strip().lower()
            if compact in placeholders:
                missing.append(field_name.replace("_text", ""))

        extracted = [
            line.strip()
            for line in "\n".join(
                [
                    payload.intake_email_text,
                    payload.contract_text,
                    payload.order_form_text,
                    payload.implementation_notes,
                    payload.security_questionnaire_text,
                ]
            ).split(".")
            if line.strip()
        ]

        has_clean_marker = contains_any(payload.intake_email_text, ["standard", "complete"])

        normalized = NormalizedCase(
            case_id=payload.case_id,
            customer_name=payload.customer_name,
            normalized_account_info={
                "account_name": payload.account_name or payload.customer_name,
                "submitted_at": payload.submitted_at.isoformat(),
                "has_clean_marker": has_clean_marker,
            },
            document_refs=[
                DocumentRef(
                    document_id=f"doc-{payload.case_id}-intake",
                    document_type="intake_email",
                    source_name="intake_email_text",
                    content_hash=payload.intake_email_text[:16],
                ),
                DocumentRef(
                    document_id=f"doc-{payload.case_id}-contract",
                    document_type="contract",
                    source_name="contract_text",
                    content_hash=payload.contract_text[:16],
                ),
                DocumentRef(
                    document_id=f"doc-{payload.case_id}-order",
                    document_type="order_form",
                    source_name="order_form_text",
                    content_hash=payload.order_form_text[:16],
                ),
            ],
            extracted_requirements=extracted[:12],
            missing_info=missing,
            package_complete=not missing,
            risk_signals=[],
            metadata={"case_id": payload.case_id},
        )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="intake_normalization",
            agent_name="IntakeNormalizationAgent",
            inputs_summary="fields=5",
            outputs_summary=f"missing={len(missing)} package_complete={normalized.package_complete}",
            start_time=start,
        )
        return NormalizationResult(normalized_case=normalized, trace=trace)
