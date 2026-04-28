from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


OpportunityStage = Literal["presolicitation", "final_solicitation"]
Decision = Literal[
    "bid",
    "no_bid",
    "need_more_data",
    "pursue",
    "pursue_with_conditions",
    "hold_pending_information",
    "do_not_pursue",
]
Department = Literal["legal", "security", "finance", "implementation"]
ReviewStatus = Literal[
    "approved",
    "approved_with_conditions",
    "needs_info",
    "blocker",
    "worth_pursuing",
    "worth_pursuing_with_conditions",
    "hold_pending_information",
    "do_not_pursue",
]


class RealCaseSpecialistReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: Department
    reviewer_role: str
    status: ReviewStatus
    decision: str
    conditions: list[str]
    open_questions: list[str]
    evidence_finding_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class RealCaseAiSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    executive_summary: str
    opportunity_summary: str
    specialist_summary: list[str]
    conditions: list[str]
    open_questions: list[str]
    rationale: str


class RealCaseBdOpsDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    decision_owner: str
    owner_note: str
    next_steps: list[str]
    stop_conditions: list[str]


class RealCaseCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    completed_at: str
    specialist_reviews: list[RealCaseSpecialistReview]
    ai_synthesis: RealCaseAiSynthesis
    bd_ops_decision: RealCaseBdOpsDecision
    audit_events: list[dict[str, str]]


def main() -> None:
    _ensure_project_root()
    from app.settings import get_settings

    parser = argparse.ArgumentParser(
        description="Complete a real AI FlowOps case through specialist reviews, AI synthesis, and BD/Ops decision."
    )
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--decision-owner", default="BD/Ops Lead")
    parser.add_argument("--codex-command")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-timeout-seconds", type=int)
    args = parser.parse_args()

    case_dir = args.case_dir.resolve()
    state_path = case_dir / "ai_flowops_state.local.json"
    if not state_path.is_file():
        raise SystemExit(f"Missing AI FlowOps state. Run prepare_real_case.py first: {state_path}")

    settings = get_settings()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    opportunity_stage = _opportunity_stage(state)
    specialist_reviews = _build_specialist_reviews(state, opportunity_stage)
    synthesis = _run_ai_synthesis(
        state=state,
        specialist_reviews=specialist_reviews,
        opportunity_stage=opportunity_stage,
        codex_command=args.codex_command or settings.codex_command,
        codex_model=args.codex_model or settings.codex_model,
        timeout_seconds=args.codex_timeout_seconds or settings.codex_timeout_seconds,
    )
    bd_ops_decision = _decide_bd_ops(synthesis, args.decision_owner, opportunity_stage)
    completion = RealCaseCompletion(
        case_id=state["case_id"],
        completed_at=datetime.now(UTC).isoformat(),
        specialist_reviews=specialist_reviews,
        ai_synthesis=synthesis,
        bd_ops_decision=bd_ops_decision,
        audit_events=_audit_events(state, specialist_reviews, synthesis, bd_ops_decision),
    )
    _write_completion(case_dir, state, completion)
    print(f"completed={state['case_id']}")
    print(f"opportunity_stage={opportunity_stage}")
    print(f"ai_recommendation={completion.ai_synthesis.recommendation}")
    print(f"bd_ops_decision={completion.bd_ops_decision.decision}")
    print(f"reviews={len(completion.specialist_reviews)}")
    print(f"report={case_dir / 'ai_flowops_completed_case.local.md'}")


def _build_specialist_reviews(
    state: dict[str, Any],
    opportunity_stage: OpportunityStage,
) -> list[RealCaseSpecialistReview]:
    by_department: dict[str, list[dict[str, Any]]] = {dept: [] for dept in _departments()}
    for finding in state.get("findings", []):
        route = finding.get("route")
        if route in by_department:
            by_department[route].append(finding)

    return [
        _review_department(department, findings, opportunity_stage)
        for department, findings in by_department.items()
        if findings
    ]


def _review_department(
    department: Department,
    findings: list[dict[str, Any]],
    opportunity_stage: OpportunityStage,
) -> RealCaseSpecialistReview:
    if opportunity_stage == "presolicitation":
        return _review_presolicitation_department(department, findings)

    return _review_final_solicitation_department(department, findings)


def _review_final_solicitation_department(
    department: Department,
    findings: list[dict[str, Any]],
) -> RealCaseSpecialistReview:
    high_count = sum(1 for finding in findings if finding.get("severity") in {"high", "critical"})
    evidence_ids = [str(finding["finding_id"]) for finding in findings]

    if department == "legal":
        status: ReviewStatus = "blocker" if high_count >= 4 else "approved_with_conditions"
        conditions = [
            (
                "Confirm award vehicle, non-negotiable data-rights terms, OCI exposure, "
                "foreign participation limits, and export-control registration before any bid decision."
            )
        ]
        open_questions = [
            "Can the company accept non-negotiable SBIR/ARA data-rights terms?",
            "Is there any SETA/A&AS or foreign-participation conflict?",
        ]
    elif department == "security":
        status = "needs_info" if high_count else "approved_with_conditions"
        conditions = [
            "Confirm clearance, safeguarding, DISA cloud authorization, and export-controlled data handling capability."
        ]
        open_questions = [
            "Does the delivery team already have required facility/personnel clearances?",
            "Will any cloud service hold government or government-related data?",
        ]
    elif department == "finance":
        status = "needs_info"
        conditions = [
            (
                "Model cost-share exposure and confirm government-approved accounting-system "
                "readiness before proposal spend."
            )
        ]
        open_questions = [
            "Does the team qualify for reduced cost-share treatment?",
            "Is a government-approved accounting system already in place?",
        ]
    else:
        status = "needs_info" if high_count else "approved_with_conditions"
        conditions = [
            "Request a scoped technical plan before committing proposal resources."
        ]
        open_questions = [
            "Can the team support SDR gateware/firmware/cyber-control work?",
            "Does the white-paper stage provide enough scope to estimate delivery risk?",
        ]

    if status == "blocker":
        decision = (
            f"{department.title()} review found bid-blocking issues unless the open questions "
            "are resolved before qualification."
        )
    elif status == "needs_info":
        decision = (
            f"{department.title()} review cannot approve bid qualification until required "
            "capability and cost details are confirmed."
        )
    else:
        decision = f"{department.title()} review can proceed only with the listed conditions."

    return RealCaseSpecialistReview(
        department=department,
        reviewer_role=f"{department.title()} reviewer",
        status=status,
        decision=decision,
        conditions=conditions,
        open_questions=open_questions,
        evidence_finding_ids=evidence_ids,
        confidence=0.9 if high_count else 0.82,
    )


def _review_presolicitation_department(
    department: Department,
    findings: list[dict[str, Any]],
) -> RealCaseSpecialistReview:
    high_count = sum(1 for finding in findings if finding.get("severity") in {"high", "critical"})
    evidence_ids = [str(finding["finding_id"]) for finding in findings]
    hard_blocker = _has_hard_pursuit_blocker(findings)

    if hard_blocker:
        status: ReviewStatus = "do_not_pursue"
    elif high_count:
        status = "worth_pursuing_with_conditions"
    else:
        status = "worth_pursuing"

    if department == "legal":
        conditions = [
            (
                "Confirm eligibility, award vehicle fit, data-rights terms, OCI exposure, "
                "foreign participation limits, and export-control registration before final "
                "bid commitment."
            )
        ]
        open_questions = [
            "Are any eligibility, SETA/A&AS, OCI, or foreign-participation limits disqualifying?",
            "Can the company accept the expected SBIR/ARA data-rights and export-control terms?",
        ]
        default_decision = (
            "Legal sees this as worth pursuing for capture review if the listed legal gates "
            "are resolved before any final bid commitment."
        )
    elif department == "security":
        conditions = [
            (
                "Confirm clearance posture, safeguarding obligations, DISA/cloud authorization "
                "needs, and export-controlled data handling before proposal resources scale."
            )
        ]
        open_questions = [
            "Does the delivery team already have the facility/personnel clearance posture required?",
            "Will any cloud service store or process government or government-related data?",
        ]
        default_decision = (
            "Security sees this as worth pursuing if clearance, cloud, and data-handling "
            "requirements are feasible."
        )
    elif department == "finance":
        conditions = [
            (
                "Model cost-share exposure, funding uncertainty, and accounting-system readiness "
                "before authorizing full proposal spend."
            )
        ]
        open_questions = [
            "Does the company qualify for reduced cost-share treatment?",
            "Is a government-approved accounting system already in place or obtainable in time?",
        ]
        default_decision = (
            "Finance sees this as worth pursuing if cost-share and accounting requirements "
            "fit the expected opportunity value."
        )
    else:
        conditions = [
            (
                "Confirm technical scope fit, staffing assumptions, and feasibility of SDR, "
                "firmware, cyber-control, or integration work before bid commitment."
            )
        ]
        open_questions = [
            "Can the team support the likely SDR gateware, firmware, and cyber-control work?",
            "Does the presolicitation provide enough scope to estimate capture and delivery risk?",
        ]
        default_decision = (
            "Implementation sees this as worth pursuing if technical scope and staffing "
            "assumptions remain plausible during capture."
        )

    if status == "do_not_pursue":
        decision = (
            f"{department.title()} found a possible hard pursuit blocker. Do not pursue unless "
            "the blocker is disproven or materially changes."
        )
    else:
        decision = default_decision

    return RealCaseSpecialistReview(
        department=department,
        reviewer_role=f"{department.title()} reviewer",
        status=status,
        decision=decision,
        conditions=conditions,
        open_questions=open_questions,
        evidence_finding_ids=evidence_ids,
        confidence=0.88 if high_count else 0.8,
    )


def _has_hard_pursuit_blocker(findings: list[dict[str, Any]]) -> bool:
    blocker_terms = (
        "ineligible",
        "not eligible",
        "disqualif",
        "prohibit",
        "barred",
        "cannot participate",
        "not permitted",
        "impossible",
        "mandatory requirement cannot be met",
    )
    searchable = " ".join(
        f"{finding.get('rule_id', '')} {finding.get('summary', '')}".lower()
        for finding in findings
        if finding.get("severity") in {"high", "critical"}
    )
    return any(term in searchable for term in blocker_terms)


def _run_ai_synthesis(
    *,
    state: dict[str, Any],
    specialist_reviews: list[RealCaseSpecialistReview],
    opportunity_stage: OpportunityStage,
    codex_command: str,
    codex_model: str,
    timeout_seconds: int,
) -> RealCaseAiSynthesis:
    schema = RealCaseAiSynthesis.model_json_schema()
    prompt = _synthesis_prompt(state, specialist_reviews, opportunity_stage)
    with tempfile.TemporaryDirectory(prefix="ai-flowops-real-synthesis-") as temp_dir:
        schema_path = Path(temp_dir) / "schema.json"
        output_path = Path(temp_dir) / "result.json"
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        command = [
            _resolve_executable(codex_command),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--model",
            codex_model,
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
            raise RuntimeError(f"Codex synthesis failed with exit {completed.returncode}: {stderr}")
        return RealCaseAiSynthesis.model_validate_json(output_path.read_text(encoding="utf-8"))


def _synthesis_prompt(
    state: dict[str, Any],
    specialist_reviews: list[RealCaseSpecialistReview],
    opportunity_stage: OpportunityStage,
) -> str:
    findings = [
        {
            "finding_id": finding.get("finding_id"),
            "route": finding.get("route"),
            "severity": finding.get("severity"),
            "summary": finding.get("summary"),
            "evidence": [
                {
                    "source": evidence.get("source_document_type"),
                    "locator": evidence.get("locator"),
                    "quote": evidence.get("quote"),
                    "fact": evidence.get("normalized_fact"),
                }
                for evidence in finding.get("evidence", [])
            ],
        }
        for finding in state.get("findings", [])
        if finding.get("route") != "auto_approve"
    ]
    if opportunity_stage == "presolicitation":
        instructions = (
            "You are the AI synthesis layer for a governed presolicitation pursuit workflow. "
            "Use the actual specialist reviews and grounded findings below. The decision is not "
            "whether to submit a final bid today; it is whether BD/Ops should pursue the "
            "opportunity, prepare for the next solicitation step, and assign capture follow-ups. "
            "Recommend exactly one of: pursue, pursue_with_conditions, hold_pending_information, "
            "do_not_pursue. Missing final solicitation details are normal for presolicitations; "
            "treat them as conditions or open questions unless the evidence shows a true hard "
            "pursuit blocker. Prefer pursue_with_conditions when the opportunity is plausible "
            "and department gates can be worked during capture."
        )
    else:
        instructions = (
            "You are the AI synthesis layer for a governed bid/no-bid workflow. Use the actual "
            "specialist reviews and grounded findings below. Recommend exactly one of: bid, "
            "no_bid, need_more_data. If material legal, security, finance, or implementation "
            "prerequisites are unresolved, prefer need_more_data over bid."
        )

    return (
        f"{instructions} Return only JSON matching the supplied schema.\n\n"
        f"Opportunity stage: {opportunity_stage}\n"
        f"Case id: {state.get('case_id')}\n"
        f"Account: {state.get('intake', {}).get('account_name')}\n\n"
        "Specialist reviews:\n"
        f"{json.dumps([review.model_dump() for review in specialist_reviews], indent=2)}\n\n"
        "Grounded findings:\n"
        f"{json.dumps(findings, indent=2)}"
    )


def _decide_bd_ops(
    synthesis: RealCaseAiSynthesis,
    decision_owner: str,
    opportunity_stage: OpportunityStage,
) -> RealCaseBdOpsDecision:
    if opportunity_stage == "presolicitation":
        return _decide_presolicitation_bd_ops(synthesis, decision_owner)

    if synthesis.recommendation == "bid":
        return RealCaseBdOpsDecision(
            decision="bid",
            decision_owner=decision_owner,
            owner_note="Proceed to qualification with the AI synthesis conditions assigned to owners.",
            next_steps=[
                "Assign proposal owner.",
                "Create owner tasks for each condition.",
                "Schedule bid/no-bid checkpoint after conditions are resolved.",
            ],
            stop_conditions=synthesis.open_questions,
        )
    if synthesis.recommendation == "no_bid":
        return RealCaseBdOpsDecision(
            decision="no_bid",
            decision_owner=decision_owner,
            owner_note="Do not pursue until blockers change materially.",
            next_steps=[
                "Archive opportunity decision record.",
                "Notify BD owner and capture lessons for future screening.",
            ],
            stop_conditions=synthesis.conditions + synthesis.open_questions,
        )
    return RealCaseBdOpsDecision(
        decision="need_more_data",
        decision_owner=decision_owner,
        owner_note="Hold final bid/no-bid commitment until the open specialist questions are resolved.",
        next_steps=[
            "Send Legal/Security/Finance/Implementation questions to accountable owners.",
            "Re-run BD/Ops decision after responses are received.",
            "Do not commit proposal resources beyond qualification research.",
        ],
        stop_conditions=synthesis.open_questions,
    )


def _decide_presolicitation_bd_ops(
    synthesis: RealCaseAiSynthesis,
    decision_owner: str,
) -> RealCaseBdOpsDecision:
    if synthesis.recommendation == "pursue":
        return RealCaseBdOpsDecision(
            decision="pursue",
            decision_owner=decision_owner,
            owner_note=(
                "Proceed to capture review and prepare for the next solicitation step. "
                "Do not treat this as final bid authorization."
            ),
            next_steps=[
                "Assign capture owner.",
                "Track final solicitation release.",
                "Prepare department follow-up list before bid/no-bid commitment.",
            ],
            stop_conditions=synthesis.open_questions,
        )
    if synthesis.recommendation == "do_not_pursue":
        return RealCaseBdOpsDecision(
            decision="do_not_pursue",
            decision_owner=decision_owner,
            owner_note="Do not pursue unless the hard pursuit blocker materially changes.",
            next_steps=[
                "Archive opportunity decision record.",
                "Notify BD owner and capture reason for future screening.",
            ],
            stop_conditions=synthesis.conditions + synthesis.open_questions,
        )
    if synthesis.recommendation == "hold_pending_information":
        return RealCaseBdOpsDecision(
            decision="hold_pending_information",
            decision_owner=decision_owner,
            owner_note=(
                "Hold capture investment beyond monitoring until the listed information is "
                "confirmed."
            ),
            next_steps=[
                "Monitor the opportunity for updates.",
                "Send targeted questions to accountable owners.",
                "Re-run pursuit review when missing information is available.",
            ],
            stop_conditions=synthesis.open_questions,
        )
    return RealCaseBdOpsDecision(
        decision="pursue_with_conditions",
        decision_owner=decision_owner,
        owner_note=(
            "Proceed to capture review; do not commit full proposal resources until listed "
            "gates are resolved."
        ),
        next_steps=[
            "Assign capture owner.",
            "Create Legal/Security/Finance/Implementation follow-up tasks.",
            "Prepare for the next solicitation step.",
            "Schedule final bid/no-bid checkpoint after the solicitation is released.",
        ],
        stop_conditions=synthesis.open_questions,
    )


def _audit_events(
    state: dict[str, Any],
    specialist_reviews: list[RealCaseSpecialistReview],
    synthesis: RealCaseAiSynthesis,
    decision: RealCaseBdOpsDecision,
) -> list[dict[str, str]]:
    events = [
        {
            "timestamp": "12:01 AM",
            "actor": "AI intake",
            "event_type": "documents.extracted",
            "summary": "Government PDFs extracted and normalized into a real-case packet.",
        },
        {
            "timestamp": "12:10 AM",
            "actor": "CodexReviewAgent",
            "event_type": "ai.findings.generated",
            "summary": f"{len(state.get('findings', []))} findings generated and routed.",
        },
    ]
    review_times = {
        "legal": "10:30 AM",
        "security": "10:42 AM",
        "finance": "10:53 AM",
        "implementation": "11:05 AM",
    }
    for review in specialist_reviews:
        events.append(
            {
                "timestamp": review_times[review.department],
                "actor": review.reviewer_role,
                "event_type": "specialist.review.completed",
                "summary": f"{review.department.title()} returned {review.status}.",
            }
        )
    events.extend(
        [
            {
                "timestamp": "11:18 AM",
                "actor": "AI synthesis",
                "event_type": "ai.synthesis.generated",
                "summary": f"AI recommended {synthesis.recommendation}.",
            },
            {
                "timestamp": "11:30 AM",
                "actor": decision.decision_owner,
                "event_type": "bd_ops.decision.logged",
                "summary": f"BD/Ops logged final decision: {decision.decision}.",
            },
        ]
    )
    return events


def _write_completion(
    case_dir: Path,
    state: dict[str, Any],
    completion: RealCaseCompletion,
) -> None:
    json_path = case_dir / "ai_flowops_completed_case.local.json"
    report_path = case_dir / "ai_flowops_completed_case.local.md"
    json_path.write_text(completion.model_dump_json(indent=2), encoding="utf-8")
    report_path.write_text(_render_completion_report(state, completion), encoding="utf-8")


def _render_completion_report(
    state: dict[str, Any],
    completion: RealCaseCompletion,
) -> str:
    lines = [
        f"# Completed AI FlowOps real case: {completion.case_id}",
        "",
        f"Opportunity stage: {_opportunity_stage(state)}",
        "",
        "## BD/Ops decision",
        f"- Decision: {completion.bd_ops_decision.decision}",
        f"- Owner: {completion.bd_ops_decision.decision_owner}",
        f"- Owner note: {completion.bd_ops_decision.owner_note}",
        "",
        "## AI synthesis",
        f"- Recommendation: {completion.ai_synthesis.recommendation}",
        f"- Confidence: {completion.ai_synthesis.confidence}",
        f"- Executive summary: {completion.ai_synthesis.executive_summary}",
        f"- Opportunity summary: {completion.ai_synthesis.opportunity_summary}",
        f"- Rationale: {completion.ai_synthesis.rationale}",
        "",
        "## Conditions",
    ]
    lines.extend(f"- {item}" for item in completion.ai_synthesis.conditions or ["None"])
    lines.append("")
    lines.append("## Open questions")
    lines.extend(f"- {item}" for item in completion.ai_synthesis.open_questions or ["None"])
    lines.append("")
    lines.append("## Specialist reviews")
    findings_by_id = {finding["finding_id"]: finding for finding in state.get("findings", [])}
    for review in completion.specialist_reviews:
        lines.extend(
            [
                f"### {review.department.title()}",
                f"- Status: {review.status}",
                f"- Decision: {review.decision}",
                f"- Conditions: {'; '.join(review.conditions) or 'None'}",
                f"- Open questions: {'; '.join(review.open_questions) or 'None'}",
                "- Supporting findings:",
            ]
        )
        for finding_id in review.evidence_finding_ids:
            finding = findings_by_id.get(finding_id, {})
            lines.append(f"  - {finding_id}: {finding.get('summary', '')}")
    lines.extend(["", "## Audit trail"])
    lines.extend(
        f"- {event['timestamp']} | {event['actor']} | {event['event_type']} | {event['summary']}"
        for event in completion.audit_events
    )
    return "\n".join(lines).strip() + "\n"


def _departments() -> tuple[Department, ...]:
    return ("legal", "security", "finance", "implementation")


def _opportunity_stage(state: dict[str, Any]) -> OpportunityStage:
    metadata = state.get("intake", {}).get("metadata") or {}
    stage = str(metadata.get("opportunity_stage") or "final_solicitation").strip().lower()
    if stage in {"presolicitation", "pre_solicitation", "pre-solicitation", "synopsis"}:
        return "presolicitation"
    return "final_solicitation"


def _resolve_executable(command: str) -> str:
    if os.name == "nt" and not command.lower().endswith((".exe", ".cmd", ".bat")):
        for candidate in (f"{command}.cmd", f"{command}.exe", command):
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return command


if __name__ == "__main__":
    main()
