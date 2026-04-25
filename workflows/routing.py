from collections.abc import Sequence

from schemas.case import Finding, Route, Severity

ROUTES: tuple[Route, ...] = (
    "auto_approve",
    "legal",
    "security",
    "implementation",
    "finance",
)

ESCALATION_ROUTES: tuple[Route, ...] = (
    "legal",
    "security",
    "implementation",
    "finance",
)

ROUTE_SEVERITY: dict[Route, int] = {
    "auto_approve": 0,
    "finance": 1,
    "implementation": 2,
    "security": 3,
    "legal": 4,
}


def approval_required(
    severity: Severity,
    confidence: float,
    missing_required_info: bool = False,
    has_conflicting_evidence: bool = False,
) -> bool:
    return (
        severity in {"high", "critical"}
        or confidence < 0.75
        or missing_required_info
        or has_conflicting_evidence
    )


def choose_route(
    findings: Sequence[Finding] | Sequence[str],
    confidence: float = 1.0,
    missing_required_info: bool = False,
    requested_route: Route | None = None,
    has_conflicting_evidence: bool = False,
) -> tuple[Route, bool, list[Route]]:
    normalized = []
    for item in findings:
        if isinstance(item, str):
            normalized.append(
                Finding(
                    finding_id=f"tmp-{item}",
                    rule_id=f"tmp-{item}",
                    finding_type="spec",
                    severity="low",
                    route="auto_approve",
                    summary=item,
                    evidence=[],
                    confidence=0.5,
                    source_agent="test",
                )
            )
        else:
            normalized.append(item)

    if requested_route in ESCALATION_ROUTES:
        return (
            requested_route,
            approval_required(
                _max_severity_from_findings(normalized),
                confidence,
                missing_required_info,
                has_conflicting_evidence,
            ),
            [],
        )

    if not normalized:
        return (
            "auto_approve",
            approval_required("low", confidence, missing_required_info, has_conflicting_evidence),
            [],
        )

    sorted_findings = sorted(
        normalized, key=lambda item: _severity_rank(item.severity), reverse=True
    )
    top = sorted_findings[0]
    chosen = top.route

    if chosen in ESCALATION_ROUTES:
        approval = True
    elif top.severity in {"high", "critical"}:
        approval = True
    else:
        approval = approval_required(
            top.severity,
            confidence,
            missing_required_info,
            has_conflicting_evidence,
        )

    secondary = []
    if len(sorted_findings) > 1:
        seen: set[Route] = {chosen}
        for item in sorted_findings[1:]:
            if item.route in seen:
                continue
            seen.add(item.route)
            secondary.append(item.route)

    return chosen, approval, secondary


def infer_final_route_from_tokens(route_tokens: Sequence[Route]) -> Route:
    return (
        max(route_tokens, key=lambda item: ROUTE_SEVERITY[item]) if route_tokens else "auto_approve"
    )


def _max_severity_from_findings(findings: Sequence[Finding]) -> Severity:
    if not findings:
        return "low"
    return max((finding.severity for finding in findings), key=_severity_rank)


def _severity_rank(severity: Severity) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}[severity]
