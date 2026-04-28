from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agents.base import build_trace
from schemas.case import EvidenceSpan, Finding, IntakePackage, Route, Severity, TraceRecord

SYSTEM_PROMPT = (
    "You are an AI commercial operations reviewer. Extract grounded evidence and "
    "business risk findings from synthetic intake documents. Every evidence.quote "
    "must be copied as an exact, contiguous substring from the named document. Do "
    "not paraphrase quotes, summarize quotes, combine text from multiple places, or "
    "invent wording. If a finding cannot be supported by an exact quote, omit it. "
    "Actively look for non-standard commercial intake risks: high discounts, custom "
    "credits, unusual penalties, liability-cap exceptions, nonstandard indemnity, "
    "conflicting terms, missing DPA, data residency, regulated data, unsupported "
    "integrations, aggressive timelines, unclear owners, and missing statements of "
    "work. When those risks appear, return one evidence item and one finding per "
    "material risk. Use stable snake_case rule_id values such as "
    "discount_above_threshold, custom_sla_credits, liability_cap_above_standard, "
    "nonstandard_indemnity, missing_dpa_for_regulated_data, data_residency_request, "
    "unsupported_integration, aggressive_go_live_date, and unclear_customer_owner."
)

PRESOLICITATION_CONTEXT_PROMPT = (
    "Opportunity stage: presolicitation. Analyze this as a pre-bid pursuit and "
    "capture-readiness decision, not as a final bid/no-bid decision. The business "
    "question is whether the company should pursue this opportunity and prepare for "
    "the next solicitation step. Missing final solicitation details are normal at "
    "this stage; treat them as follow-up gates or open questions unless the source "
    "documents show a true hard blocker. Distinguish normal presolicitation unknowns, "
    "department follow-up gates, serious pursuit risks, and true do-not-pursue "
    "blockers. Route each material issue to Legal, Security, Finance, or "
    "Implementation using pursuit-readiness language."
)

FINAL_SOLICITATION_CONTEXT_PROMPT = (
    "Opportunity stage: final_solicitation. Analyze this as a bid-stage commercial "
    "intake package where unresolved legal, security, finance, or implementation "
    "risks can affect bid/no-bid readiness."
)


class AIReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_type: str
    locator: str
    quote: str
    normalized_fact: str
    confidence: float = Field(ge=0.0, le=1.0)


class AIReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    finding_type: str
    severity: Severity
    route: Route
    summary: str
    evidence_quotes: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class AIReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[AIReviewEvidence]
    findings: list[AIReviewFinding]
    risk_signals: list[str]
    rationale: str


CodexRunner = Callable[[str, dict[str, Any], int], AIReviewResult]


class CodexReviewAgent:
    provider_label = "openai-codex"

    def __init__(
        self,
        *,
        model: str,
        command: str = "codex",
        timeout_seconds: int = 60,
        runner: CodexRunner | None = None,
    ) -> None:
        self.model = model
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.runner = runner or self._run_codex

    def run(self, payload: IntakePackage) -> tuple[list[EvidenceSpan], list[Finding], TraceRecord]:
        start = time.perf_counter()
        parsed = self.runner(
            _build_prompt(payload),
            AIReviewResult.model_json_schema(),
            self.timeout_seconds,
        )

        evidence = [
            EvidenceSpan(
                source_document_type=item.source_document_type,
                locator=item.locator,
                quote=item.quote,
                normalized_fact=item.normalized_fact,
                confidence=item.confidence,
            )
            for item in parsed.evidence
        ]
        evidence = _ground_evidence_quotes(evidence, payload)

        findings: list[Finding] = []
        for index, item in enumerate(parsed.findings, start=1):
            finding_evidence = _evidence_for_quotes(evidence, item.evidence_quotes)
            if item.route != "auto_approve" and not finding_evidence:
                continue
            findings.append(
                Finding(
                    finding_id=f"{payload.case_id}-ai-{index:02d}-{item.rule_id}",
                    rule_id=item.rule_id,
                    finding_type=item.finding_type,
                    severity=item.severity,
                    route=item.route,
                    summary=item.summary,
                    evidence=finding_evidence,
                    confidence=item.confidence,
                    source_agent="CodexReviewAgent",
                )
            )

        trace = build_trace(
            case_id=payload.case_id,
            step_name="codex_document_review",
            agent_name="CodexReviewAgent",
            inputs_summary=f"documents={len(_document_texts(payload))}",
            outputs_summary=f"evidence={len(evidence)} findings={len(findings)}",
            start_time=start,
        ).model_copy(update={"model_provider_label": self.provider_label})
        return evidence, findings, trace

    def _run_codex(self, prompt: str, schema: dict[str, Any], timeout_seconds: int) -> AIReviewResult:
        with tempfile.TemporaryDirectory(prefix="ai-flowops-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "result.json"
            schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
            command = [
                _resolve_executable(self.command),
                "--ask-for-approval",
                "never",
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--model",
                self.model,
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "--",
                "-",
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                input=prompt,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=timeout_seconds,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.strip()[-1000:]
                raise RuntimeError(f"Codex review failed with exit {completed.returncode}: {stderr}")
            if not output_path.exists():
                raise RuntimeError("Codex review did not write structured output.")
            return AIReviewResult.model_validate_json(output_path.read_text(encoding="utf-8"))


def _document_texts(payload: IntakePackage) -> list[tuple[str, str]]:
    if payload.source_documents:
        return [
            (document.document_type, document.content or "")
            for document in payload.source_documents
        ]
    return [
        ("intake_email", payload.intake_email_text),
        ("contract", payload.contract_text),
        ("order_form", payload.order_form_text),
        ("implementation_notes", payload.implementation_notes),
        ("security_questionnaire", payload.security_questionnaire_text),
    ]


def _format_documents(payload: IntakePackage) -> str:
    return "\n\n".join(
        f"## {document_type}\n{text}"
        for document_type, text in _document_texts(payload)
    )


def _build_prompt(payload: IntakePackage) -> str:
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"{_opportunity_stage_prompt(payload)}\n\n"
        "Return only JSON matching the supplied schema. Do not edit files. Do not run tools.\n\n"
        f"Case id: {payload.case_id}\n"
        f"Customer: {payload.customer_name}\n\n"
        f"{_format_documents(payload)}"
    )


def _opportunity_stage(payload: IntakePackage) -> str:
    stage = str(payload.metadata.get("opportunity_stage") or "final_solicitation").strip().lower()
    if stage in {"presolicitation", "pre_solicitation", "pre-solicitation", "synopsis"}:
        return "presolicitation"
    return "final_solicitation"


def _opportunity_stage_prompt(payload: IntakePackage) -> str:
    if _opportunity_stage(payload) == "presolicitation":
        return PRESOLICITATION_CONTEXT_PROMPT
    return FINAL_SOLICITATION_CONTEXT_PROMPT


def _resolve_executable(command: str) -> str:
    if os.name == "nt" and not command.lower().endswith((".exe", ".cmd", ".bat")):
        for candidate in (f"{command}.cmd", f"{command}.exe", command):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return command


def _ground_evidence_quotes(evidence: list[EvidenceSpan], payload: IntakePackage) -> list[EvidenceSpan]:
    text_by_type = {document_type: text for document_type, text in _document_texts(payload)}
    grounded: list[EvidenceSpan] = []
    for item in evidence:
        source_document_type = _canonical_document_type(item.source_document_type, text_by_type)
        source_text = text_by_type.get(source_document_type, "")
        if _contains_quote(source_text, item.quote):
            grounded.append(item.model_copy(update={"source_document_type": source_document_type}))
            continue
        replacement = _best_source_sentence(
            source_text,
            search_text=f"{item.quote} {item.normalized_fact}",
        )
        if replacement is not None:
            grounded.append(
                item.model_copy(
                    update={
                        "source_document_type": source_document_type,
                        "quote": replacement,
                    }
                )
            )
            continue
        source_document_type, replacement = _best_packet_sentence(
            text_by_type,
            search_text=f"{item.quote} {item.normalized_fact}",
        )
        if replacement is None or source_document_type is None:
            raise ValueError(f"AI evidence quote is not grounded: {item.normalized_fact}")
        grounded.append(
            item.model_copy(
                update={
                    "source_document_type": source_document_type,
                    "quote": replacement,
                }
            )
        )
    return grounded


def _canonical_document_type(document_type: str, text_by_type: dict[str, str]) -> str:
    if document_type in text_by_type:
        return document_type
    aliases = {
        "security": "security_questionnaire",
        "questionnaire": "security_questionnaire",
        "security_review": "security_questionnaire",
        "implementation": "implementation_notes",
        "delivery": "implementation_notes",
        "order": "order_form",
        "pricing": "order_form",
        "commercial": "order_form",
        "terms": "contract",
        "legal": "contract",
        "email": "intake_email",
        "intake": "intake_email",
    }
    return aliases.get(document_type.lower(), document_type)


def _contains_quote(source_text: str, quote: str) -> bool:
    return _normalize_text(quote) in _normalize_text(source_text)


def _best_source_sentence(source_text: str, search_text: str) -> str | None:
    terms = _search_terms(search_text)
    if not terms:
        return None

    best_sentence = ""
    best_score = 0
    for sentence in _source_sentences(source_text):
        sentence_terms = set(_search_terms(sentence))
        score = len(terms.intersection(sentence_terms))
        if score > best_score:
            best_score = score
            best_sentence = sentence

    minimum_score = 2 if len(terms) >= 2 else 1
    if best_score < minimum_score:
        return None
    return best_sentence


def _best_packet_sentence(
    text_by_type: dict[str, str],
    search_text: str,
) -> tuple[str | None, str | None]:
    best_document_type = None
    best_sentence = None
    best_score = 0
    terms = _search_terms(search_text)
    for document_type, source_text in text_by_type.items():
        for sentence in _source_sentences(source_text):
            sentence_terms = set(_search_terms(sentence))
            score = len(terms.intersection(sentence_terms))
            if score > best_score:
                best_score = score
                best_document_type = document_type
                best_sentence = sentence

    minimum_score = 2 if len(terms) >= 2 else 1
    if best_score < minimum_score:
        return None, None
    return best_document_type, best_sentence


def _source_sentences(source_text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", source_text).strip()
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def _search_terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"\d+%?|[a-zA-Z][a-zA-Z_'-]{2,}", text.lower())
        if term not in {"the", "and", "for", "that", "with", "from", "this", "will", "are", "has"}
    }


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _evidence_for_quotes(
    evidence: list[EvidenceSpan],
    quotes: list[str],
) -> list[EvidenceSpan]:
    if not quotes:
        return []
    quote_set = {quote.strip().lower() for quote in quotes}
    selected = [
        item
        for item in evidence
        if item.quote.strip().lower() in quote_set
    ]
    if selected:
        return selected

    for quote in quotes:
        quote_terms = _search_terms(quote)
        best_item = None
        best_score = 0
        for item in evidence:
            item_terms = _search_terms(f"{item.quote} {item.normalized_fact}")
            score = len(quote_terms.intersection(item_terms))
            if score > best_score:
                best_score = score
                best_item = item
        if best_item is not None and best_score >= 2 and best_item not in selected:
            selected.append(best_item)
    return selected
