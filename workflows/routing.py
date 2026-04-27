from __future__ import annotations

from collections.abc import Sequence

from schemas.case import Route, Severity

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

ROUTE_PRIORITY = {
    "auto_approve": 0,
    "finance": 1,
    "implementation": 2,
    "security": 3,
    "legal": 4,
}

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def requires_approval(
    severity: Severity, confidence: float, missing_required_info: bool = False
) -> bool:
    return bool(severity in {"high", "critical"} or confidence < 0.75 or missing_required_info)


def highest_severity(severities: Sequence[Severity]) -> Severity:
    if not severities:
        return "low"
    return max(severities, key=_severity_rank)


def choose_route(
    severities: Sequence[Severity],
    requested_route: Route | None = None,
    confidence: float = 1.0,
    missing_required_info: bool = False,
    requested_route_hint: Route | None = None,
) -> tuple[Route, bool]:
    if requested_route in ESCALATION_ROUTES:
        return requested_route, requires_approval(
            highest_severity(severities),
            confidence=confidence,
            missing_required_info=missing_required_info,
        )

    if requested_route_hint in ESCALATION_ROUTES:
        return requested_route_hint, requires_approval(
            highest_severity(severities),
            confidence=confidence,
            missing_required_info=missing_required_info,
        )

    if not severities:
        return "auto_approve", requires_approval(
            "low", confidence=confidence, missing_required_info=missing_required_info
        )

    highest = highest_severity(severities)
    if highest in {"high", "critical"}:
        route = _route_for_max_risk()
        return route, True

    if highest == "medium":
        route = (
            requested_route if requested_route in ESCALATION_ROUTES else _route_for_medium_risk()
        )
        return route, True

    # low
    return "auto_approve", requires_approval("low", confidence, missing_required_info)


def choose_route_by_votes(routes: Sequence[Route], fallback: Route = "auto_approve") -> Route:
    if not routes:
        return fallback
    weighted = {route: 0 for route in ROUTES}
    for route in routes:
        weighted[route] = weighted.get(route, 0) + 1
    return max(ROUTES, key=lambda route: (weighted.get(route, 0), ROUTE_PRIORITY[route]))


def _route_for_max_risk() -> Route:
    return "legal"


def _route_for_medium_risk() -> Route:
    return "finance"


def _severity_rank(severity: Severity) -> int:
    return SEVERITY_RANK[severity]
