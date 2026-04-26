from __future__ import annotations

from schemas.case import EvidenceSpan, Finding, IntakePackage, NormalizedCase


class CriticEvaluatorAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        intake: IntakePackage,
        normalized_case: NormalizedCase,
        evidence: list[EvidenceSpan],
        findings: list[Finding],
    ) -> list[str]:
        issues = []
        if not normalized_case.package_complete:
            issues.append("incomplete_package")
        if normalized_case.missing_info:
            issues.append("missing_info")
        if not evidence:
            issues.append("missing_evidence")
        for finding in findings:
            if not finding.evidence and finding.route != "auto_approve":
                issues.append(f"missing_evidence:{finding.rule_id}")
            elif finding.route != "auto_approve" and not _finding_has_supporting_evidence(finding):
                issues.append(f"unsupported_evidence:{finding.rule_id}")
            if finding.route != "auto_approve" and finding.severity not in {
                "low",
                "medium",
                "high",
                "critical",
            }:
                issues.append(f"invalid_severity:{finding.rule_id}")
        if (
            intake.expected_route is not None
            and intake.expected_route == "auto_approve"
            and findings
        ):
            clean_evidence = [e for e in evidence if e.confidence > 0.2]
            if not clean_evidence:
                issues.append("missing_critical_evidence")
        return issues


def _finding_has_supporting_evidence(finding: Finding) -> bool:
    terms = _support_terms(finding)
    if not terms:
        return bool(finding.evidence)
    for span in finding.evidence:
        haystack = f"{span.normalized_fact} {span.quote}".lower()
        if any(term in haystack for term in terms):
            return True
    return False


def _support_terms(finding: Finding) -> list[str]:
    raw = f"{finding.rule_id} {finding.summary}".replace("_", " ").replace("-", " ").lower()
    stopwords = {
        "for",
        "the",
        "and",
        "with",
        "route",
        "rule",
        "playbook",
        "matched",
        "requires",
        "review",
        "needs",
        "standard",
    }
    return [
        token
        for token in raw.split()
        if len(token) > 3 and token not in stopwords
    ]
