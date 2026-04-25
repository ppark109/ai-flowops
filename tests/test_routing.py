from schemas.case import Finding
from workflows.routing import choose_route


def test_clean_case_auto_approves_without_review() -> None:
    route, needs_approval, _ = choose_route([], confidence=0.96)

    assert route == "auto_approve"
    assert needs_approval is False


def test_low_confidence_clean_case_requires_approval() -> None:
    route, needs_approval, _ = choose_route([], confidence=0.70)

    assert route == "auto_approve"
    assert needs_approval is True


def test_high_severity_case_escalates_to_legal() -> None:
    route, needs_approval, _ = choose_route(
        [
            Finding(
                rule_id="x",
                finding_id="x",
                finding_type="t",
                severity="high",
                route="legal",
                summary="x",
                confidence=0.9,
                evidence=[],
                source_agent="x",
            )
        ],
        confidence=0.90,
    )

    assert route == "legal"
    assert needs_approval is True


def test_requested_specialist_route_is_preserved() -> None:
    route, needs_approval, _ = choose_route(
        [
            Finding(
                rule_id="x",
                finding_id="x",
                finding_type="t",
                severity="medium",
                route="security",
                summary="x",
                confidence=0.9,
                evidence=[],
                source_agent="x",
            )
        ],
        requested_route="finance",
        confidence=0.90,
    )

    assert route == "finance"
    assert needs_approval is False
