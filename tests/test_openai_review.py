from pathlib import Path

import pytest

from agents.openai_review import SYSTEM_PROMPT, AIReviewResult, CodexReviewAgent
from workflows.seeding import load_case_files


class _Runner:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def __call__(self, prompt, schema, timeout_seconds):
        self.calls.append(
            {
                "prompt": prompt,
                "schema": schema,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.parsed


def test_codex_review_agent_accepts_grounded_structured_output() -> None:
    case = {item.case_id: item for item in load_case_files(Path("data/seed/cases"))}[
        "seed-legal-001"
    ]
    parsed = AIReviewResult.model_validate(
        {
            "evidence": [
                {
                    "source_document_type": "contract",
                    "locator": "contract:liability",
                    "quote": "liability cap is above 1x fees",
                    "normalized_fact": "liability cap above standard",
                    "confidence": 0.94,
                }
            ],
            "findings": [
                {
                    "rule_id": "liability_cap_above_standard",
                    "finding_type": "ai_review",
                    "severity": "high",
                    "route": "legal",
                    "summary": "Liability cap exceeds the standard threshold.",
                    "evidence_quotes": ["liability cap is above 1x fees"],
                    "confidence": 0.92,
                }
            ],
            "risk_signals": ["liability_cap_above_standard"],
            "rationale": "Legal review is needed.",
        }
    )
    runner = _Runner(parsed)
    agent = CodexReviewAgent(
        model="gpt-5.5",
        runner=runner,
    )

    evidence, findings, trace = agent.run(case)

    prompt = runner.calls[0]["prompt"]
    assert SYSTEM_PROMPT in prompt
    assert "exact, contiguous substring" in prompt
    assert "Do not paraphrase quotes" in prompt
    assert "Opportunity stage: final_solicitation" in prompt
    assert "bid/no-bid readiness" in prompt
    assert len(evidence) == 1
    assert findings[0].route == "legal"
    assert findings[0].source_agent == "CodexReviewAgent"
    assert trace.step_name == "codex_document_review"
    assert trace.model_provider_label == "openai-codex"


def test_codex_review_agent_rejects_ungrounded_quotes() -> None:
    case = {item.case_id: item for item in load_case_files(Path("data/seed/cases"))}[
        "seed-legal-001"
    ]
    parsed = AIReviewResult.model_validate(
        {
            "evidence": [
                {
                    "source_document_type": "contract",
                    "locator": "contract:1",
                    "quote": "not present in the document",
                    "normalized_fact": "unsupported claim",
                    "confidence": 0.8,
                }
            ],
            "findings": [],
            "risk_signals": [],
            "rationale": "",
        }
    )
    agent = CodexReviewAgent(model="gpt-5.5", runner=_Runner(parsed))

    with pytest.raises(ValueError, match="not grounded"):
        agent.run(case)


def test_codex_review_agent_regrounds_paraphrased_quote_to_source_sentence() -> None:
    case = {item.case_id: item for item in load_case_files(Path("data/seed/cases"))}[
        "seed-finance-001"
    ]
    parsed = AIReviewResult.model_validate(
        {
            "evidence": [
                {
                    "source_document_type": "order_form",
                    "locator": "order_form:pricing",
                    "quote": "A 45% discount is requested, requiring finance review.",
                    "normalized_fact": "45% discount above threshold",
                    "confidence": 0.88,
                }
            ],
            "findings": [
                {
                    "rule_id": "discount_above_threshold",
                    "finding_type": "ai_review",
                    "severity": "medium",
                    "route": "finance",
                    "summary": "Discount requires finance review.",
                    "evidence_quotes": ["A 45% discount is requested, requiring finance review."],
                    "confidence": 0.86,
                }
            ],
            "risk_signals": ["discount_above_threshold"],
            "rationale": "",
        }
    )
    agent = CodexReviewAgent(model="gpt-5.5", runner=_Runner(parsed))

    evidence, findings, _ = agent.run(case)

    assert (
        evidence[0].quote
        == "The discount is above the standard approval threshold and must be reviewed by finance before booking."
    )
    assert findings[0].evidence[0].quote == evidence[0].quote


def test_codex_review_agent_uses_presolicitation_context() -> None:
    base_case = {item.case_id: item for item in load_case_files(Path("data/seed/cases"))}[
        "seed-legal-001"
    ]
    case = base_case.model_copy(update={"metadata": {"opportunity_stage": "presolicitation"}})
    parsed = AIReviewResult.model_validate(
        {
            "evidence": [
                {
                    "source_document_type": "contract",
                    "locator": "contract:liability",
                    "quote": "liability cap is above 1x fees",
                    "normalized_fact": "liability cap above standard",
                    "confidence": 0.94,
                }
            ],
            "findings": [
                {
                    "rule_id": "liability_cap_above_standard",
                    "finding_type": "ai_review",
                    "severity": "high",
                    "route": "legal",
                    "summary": "Liability cap should be tracked as a pursuit gate.",
                    "evidence_quotes": ["liability cap is above 1x fees"],
                    "confidence": 0.92,
                }
            ],
            "risk_signals": ["liability_cap_above_standard"],
            "rationale": "Legal follow-up is needed before bid commitment.",
        }
    )
    runner = _Runner(parsed)
    agent = CodexReviewAgent(model="gpt-5.5", runner=runner)

    _evidence, findings, _trace = agent.run(case)

    prompt = runner.calls[0]["prompt"]
    assert "Opportunity stage: presolicitation" in prompt
    assert "pre-bid pursuit and capture-readiness decision" in prompt
    assert "Missing final solicitation details are normal" in prompt
    assert "true do-not-pursue blockers" in prompt
    assert findings[0].route == "legal"


def test_codex_review_agent_regrounds_quote_when_source_document_uses_alias() -> None:
    case = {item.case_id: item for item in load_case_files(Path("data/held_out/cases"))}[
        "heldout-security-001"
    ]
    parsed = AIReviewResult.model_validate(
        {
            "evidence": [
                {
                    "source_document_type": "security",
                    "locator": "security:1",
                    "quote": "The required DPA is missing from the packet.",
                    "normalized_fact": "The required DPA is missing from the packet.",
                    "confidence": 0.88,
                }
            ],
            "findings": [
                {
                    "rule_id": "missing_dpa_for_regulated_data",
                    "finding_type": "ai_review",
                    "severity": "high",
                    "route": "security",
                    "summary": "Missing DPA requires security review.",
                    "evidence_quotes": ["The required DPA is missing from the packet."],
                    "confidence": 0.86,
                }
            ],
            "risk_signals": ["missing_dpa_for_regulated_data"],
            "rationale": "",
        }
    )
    agent = CodexReviewAgent(model="gpt-5.5", runner=_Runner(parsed))

    evidence, findings, _ = agent.run(case)

    assert evidence[0].source_document_type == "security_questionnaire"
    assert evidence[0].quote == "The DPA is missing and security artifacts are not provided."
    assert findings[0].evidence[0].quote == evidence[0].quote
