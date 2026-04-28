from scripts.complete_real_case import (
    RealCaseAiSynthesis,
    _build_specialist_reviews,
    _decide_bd_ops,
    _synthesis_prompt,
)


def _state() -> dict:
    return {
        "case_id": "FA875026S7002",
        "intake": {
            "account_name": "CORTEX presolicitation",
            "metadata": {"opportunity_stage": "presolicitation"},
        },
        "findings": [
            {
                "finding_id": "finding-legal-1",
                "rule_id": "data_rights_terms",
                "route": "legal",
                "severity": "high",
                "summary": "Data-rights terms require legal review before bid commitment.",
                "evidence": [
                    {
                        "source_document_type": "program_solicitation",
                        "locator": "page 4",
                        "quote": "Rights in technical data shall be provided.",
                        "normalized_fact": "Data-rights terms need legal review.",
                    }
                ],
            },
            {
                "finding_id": "finding-security-1",
                "rule_id": "clearance_requirements",
                "route": "security",
                "severity": "high",
                "summary": "Clearance requirements need confirmation.",
                "evidence": [],
            },
        ],
    }


def test_presolicitation_specialist_reviews_are_pursuit_oriented() -> None:
    reviews = _build_specialist_reviews(_state(), "presolicitation")

    assert {review.department for review in reviews} == {"legal", "security"}
    assert {review.status for review in reviews} == {"worth_pursuing_with_conditions"}
    assert "worth pursuing" in reviews[0].decision.lower()
    assert "before final bid commitment" in " ".join(reviews[0].conditions)


def test_presolicitation_synthesis_prompt_uses_capture_decision_frame() -> None:
    reviews = _build_specialist_reviews(_state(), "presolicitation")

    prompt = _synthesis_prompt(_state(), reviews, "presolicitation")

    assert "presolicitation pursuit workflow" in prompt
    assert "not whether to submit a final bid today" in prompt
    assert "pursue_with_conditions" in prompt
    assert "Missing final solicitation details are normal" in prompt


def test_presolicitation_bd_ops_decision_uses_pursuit_vocabulary() -> None:
    synthesis = RealCaseAiSynthesis(
        recommendation="pursue_with_conditions",
        confidence=0.86,
        executive_summary="Pursue if gates are tracked.",
        opportunity_summary="Public presolicitation with plausible strategic fit.",
        specialist_summary=["Legal and Security require follow-up."],
        conditions=["Confirm legal and security gates."],
        open_questions=["When will final solicitation be released?"],
        rationale="No confirmed hard blocker.",
    )

    decision = _decide_bd_ops(synthesis, "BD/Ops Lead", "presolicitation")

    assert decision.decision == "pursue_with_conditions"
    assert "Proceed to capture review" in decision.owner_note
    assert "do not commit full proposal resources" in decision.owner_note
    assert any("final bid/no-bid checkpoint" in step for step in decision.next_steps)
