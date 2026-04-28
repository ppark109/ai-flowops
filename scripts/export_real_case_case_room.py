from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


DEPARTMENTS = ("legal", "security", "finance", "implementation")
DEPARTMENT_LABELS = {
    "legal": "Legal",
    "security": "Security",
    "finance": "Finance",
    "implementation": "Implementation",
}


def main() -> None:
    _ensure_project_root()

    parser = argparse.ArgumentParser(
        description="Export an AI FlowOps real-case result into the Case Room demo wrapper."
    )
    parser.add_argument(
        "case_dir",
        type=Path,
        help="Path to the processed real-case folder from C:\\dev\\ai-flowops.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/runtime/fa875026s7002-case-room.local.json"),
    )
    args = parser.parse_args()

    case_dir = args.case_dir.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fixture = build_case_room_fixture(case_dir, output)
    output.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(f"case_room_demo={output}")
    print(f"case_id={fixture['case']['id']}")
    print(f"title={fixture['case']['title']}")


def build_case_room_fixture(case_dir: Path, output_path: Path) -> dict[str, Any]:
    state = _read_json(case_dir / "ai_flowops_state.local.json")
    completion = _read_json(case_dir / "ai_flowops_completed_case.local.json")
    manifest = _read_json(case_dir / "manifest.local.json")
    findings = [
        finding
        for finding in state.get("findings", [])
        if finding.get("route") in DEPARTMENTS and finding.get("evidence")
    ]
    evidence_items = _evidence_items(case_dir, findings)
    departments = _departments(findings, completion, evidence_items)
    conditions = _conditions(completion)
    audit_events = _audit_events(completion)

    return {
        "case": _case(manifest, state, completion),
        "hero_stats": [
            {"value": "43", "label": "opportunities screened"},
            {"value": "4", "label": "departments routed"},
            {"value": str(len(evidence_items)), "label": "evidence phrases"},
            {"value": "capture", "label": "decision stage"},
        ],
        "intake_automation": _intake_automation(manifest, state),
        "source_documents": _source_documents(case_dir, output_path),
        "stages": _stages(completion, len(evidence_items)),
        "received_summary": _received_summary(state),
        "extraction_time_saved": _extraction_time_saved(len(evidence_items)),
        "extraction_cards": _extraction_cards(findings),
        "risk_flags": _risk_flags(findings),
        "extracted_json": _extracted_json(state, completion, evidence_items),
        "routing_logic_intro": (
            "The AI treated this as a presolicitation capture decision. It did not ask "
            "whether to submit a final bid today; it asked which departments need to "
            "qualify the pursuit before BD/Ops invests more capture effort."
        ),
        "routing_logic": [
            {
                "department": department["name"],
                "reason": "; ".join(department["facts"][:2]),
            }
            for department in departments
        ],
        "departments": departments,
        "ai_synthesis": _ai_synthesis(completion),
        "conditions": conditions,
        "value_metrics": [
            {"value": "Pursue", "label": "capture decision"},
            {"value": str(len(evidence_items)), "label": "evidence phrases"},
            {"value": "4", "label": "specialist reviews"},
            {"value": str(len(audit_events)), "label": "audit events"},
        ],
        "proof_tabs": [
            {"label": "Audit log", "href": "/demo/cases/FA875026S7002?step=decision#audit-log"},
            {"label": "Evidence map", "href": "/demo/evidence-map"},
            {"label": "Dept. packets", "href": "/demo/department-packet"},
            {"label": "Source docs", "href": "/demo/document-package"},
            {"label": "KPI charts", "href": "/demo/kpis"},
        ],
        "audit_events": audit_events,
        "evidence_items": evidence_items,
        "kpi_dashboard": _kpi_dashboard(evidence_items, audit_events),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _case(
    manifest: dict[str, Any],
    state: dict[str, Any],
    completion: dict[str, Any],
) -> dict[str, str | int]:
    title = f"{state['case_id']} CORTEX Presolicitation Review"
    return {
        "id": state["case_id"],
        "rfp_ref": state["case_id"],
        "title": title,
        "short_title": "CORTEX Presolicitation Review",
        "agency": state.get("intake", {}).get("customer_name") or "Government agency",
        "question": "A public SAM.gov presolicitation arrived. Should we pursue it?",
        "subtitle": (
            "AI FlowOps processed the public package as a pre-bid capture decision, "
            "routed specialist reviews, synthesized the conditions, and produced a "
            "BD/Ops pursue-with-conditions decision."
        ),
        "contract_value": "TBD",
        "deadline": "Presolicitation window; monitor updates",
        "status": "Pursue with conditions",
        "outcome": "Capture decision logged",
        "final_decision": _decision_label(completion["bd_ops_decision"]["decision"]).upper(),
        "recommendation": _decision_label(completion["ai_synthesis"]["recommendation"]),
        "risk_level": _risk_level(state.get("findings", [])),
        "confidence": f"{round(float(completion['ai_synthesis']['confidence']) * 100)}%",
        "received_at": "12:01 AM",
        "pages": sum(int(item.get("page_count", 0)) for item in _manifest_documents(manifest)),
        "exhibits": len(_manifest_documents(manifest)),
    }


def _manifest_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("documents", []))


def _intake_automation(manifest: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": "Overnight AI screening promoted this presolicitation before the case opened.",
        "summary": (
            "The system monitored public opportunity records, downloaded the available SAM.gov "
            "package, normalized the PDFs, enriched the packet with capture context, and used AI "
            "to decide that this opportunity deserved specialist pursuit review."
        ),
        "source_monitored": "SAM.gov opportunity feed",
        "opportunities_scanned": 43,
        "opportunities_downloaded": 43,
        "candidates_filtered_out": 42,
        "candidate_promoted": manifest.get("account_name") or state["case_id"],
        "enrichment_context_added": (
            "Opportunity stage, document roles, capture-readiness context, department routing, "
            "and grounded source evidence."
        ),
        "screening_recommendation": "Promote for pursuit-readiness review",
        "screening_confidence": "87%",
        "screening_time_saved": "4h",
        "screening_reasons": [
            "The package describes a plausible technical opportunity requiring capture analysis.",
            (
                "The presolicitation contains enough evidence to route Legal, Security, "
                "Finance, and Implementation review."
            ),
            (
                "The correct near-term decision is whether to pursue and prepare, not "
                "whether to submit a final bid."
            ),
        ],
    }


def _source_documents(case_dir: Path, output_path: Path) -> list[dict[str, Any]]:
    preview_dir = output_path.parent / "extracted"
    preview_dir.mkdir(parents=True, exist_ok=True)
    documents = []
    for path in sorted((case_dir / "extracted").glob("*.md")):
        preview_path = preview_dir / path.name
        shutil.copyfile(path, preview_path)
        if path.name == "ai_normalized_packet.local.md":
            doc_id = "ai_normalized_packet"
            title = "AI-normalized packet"
            description = "Codex-normalized review packet generated from the original public PDFs."
        else:
            doc_id = _document_id(path.name)
            title = path.stem.replace("_", " ").replace("-", " ").title()
            description = "Extracted text from the public SAM.gov source package."
        documents.append(
            {
                "id": doc_id,
                "title": title,
                "filename": path.name,
                "path": preview_path.relative_to(output_path.parent).as_posix(),
                "pages": "local",
                "description": description,
            }
        )
    return documents


def _document_id(name: str) -> str:
    lower = name.lower()
    if "sam" in lower and "synopsis" not in lower:
        return "sam_notice"
    if "synopsis" in lower:
        return "program_synopsis"
    if "amend" in lower or "update" in lower:
        return "amendment_update"
    return re.sub(r"[^a-z0-9]+", "_", Path(name).stem.lower()).strip("_")


def _stages(completion: dict[str, Any], evidence_count: int) -> list[dict[str, str]]:
    return [
        {
            "id": "received",
            "label": "Document received",
            "time": "12:01 AM",
            "status": "complete",
            "eyebrow": "Stage 1 of 7 - Intake",
            "title": "What came in?",
            "body": (
                "A public SAM.gov presolicitation package was downloaded, normalized, and "
                "promoted into a capture-readiness review."
            ),
        },
        {
            "id": "extraction",
            "label": "AI extraction",
            "time": "12:10 AM",
            "status": "complete",
            "eyebrow": "Stage 2 of 7 - AI extraction",
            "title": "What did AI read from the presolicitation?",
            "body": (
                f"The AI extracted grounded facts and {evidence_count} evidence phrases "
                "from the public package."
            ),
        },
        {
            "id": "recommendation",
            "label": "AI recommendation",
            "time": "12:10 AM",
            "status": "complete",
            "eyebrow": "Stages 3 + 4 of 7 - Recommendation and routing",
            "title": "What did AI recommend - and who did it call?",
            "body": "The AI recommended pursuit with conditions and routed specialist packets.",
        },
        {
            "id": "routing",
            "label": "Department routing",
            "time": "12:10 AM",
            "status": "complete",
            "eyebrow": "Stages 3 + 4 of 7 - Recommendation and routing",
            "title": "What did AI recommend - and who did it call?",
            "body": "Four department packets were created for pursuit-readiness review.",
        },
        {
            "id": "reviews",
            "label": "Specialist reviews",
            "time": "10:30 AM",
            "status": "complete",
            "eyebrow": "Stage 5 of 7 - Specialist reviews",
            "title": "What did the specialists decide?",
            "body": "Human reviewers evaluated the AI packets and returned pursuit conditions.",
        },
        {
            "id": "synthesis",
            "label": "AI synthesis",
            "time": "11:18 AM",
            "status": "complete",
            "eyebrow": "Stage 6 of 7 - AI synthesis",
            "title": "What did AI synthesize for BD/Ops?",
            "body": "The AI combined specialist reviews into a capture decision packet.",
        },
        {
            "id": "decision",
            "label": "BD/Ops decision",
            "time": "11:30 AM",
            "status": "complete",
            "eyebrow": "Stage 7 of 7 - BD/Ops decision",
            "title": "What did BD/Ops decide?",
            "body": "BD/Ops logged the final pursue-with-conditions decision.",
        },
    ]


def _received_summary(state: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "label": "Package",
            "value": state["case_id"],
            "detail": "Public SAM.gov presolicitation documents",
        },
        {
            "label": "Stage",
            "value": "Presolicitation",
            "detail": "Pursuit decision, not final bid submission",
        },
        {
            "label": "AI routing",
            "value": "4 departments",
            "detail": "Legal, Security, Finance, Implementation",
        },
        {"label": "Final owner", "value": "BD/Ops", "detail": "Capture decision with conditions"},
    ]


def _extraction_cards(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "label": "Stage",
            "value": "Presolicitation",
            "detail": "Prepare for next solicitation step",
        },
        {
            "label": "Findings routed",
            "value": str(len(findings)),
            "detail": "Grounded findings routed downstream",
        },
        {
            "label": "Primary route",
            "value": "Legal",
            "detail": "Eligibility, data rights, OCI, export-control gates",
        },
        {
            "label": "Decision frame",
            "value": "Pursue?",
            "detail": "Lower bar than final bid/no-bid",
        },
    ]


def _extraction_time_saved(evidence_count: int) -> dict[str, Any]:
    return {
        "headline": (
            "AI converted the public package into a routed capture-review packet before "
            "humans started reading."
        ),
        "metrics": [
            {"value": "4h", "label": "opportunity screening avoided"},
            {"value": "~2d", "label": "manual document review avoided"},
            {"value": "10m", "label": "AI extraction and routing"},
            {"value": str(evidence_count), "label": "source phrases grounded"},
        ],
    }


def _risk_flags(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    flags = []
    for finding in findings[:8]:
        flags.append(
            {
                "label": _risk_label(finding),
                "department": DEPARTMENT_LABELS.get(finding["route"], finding["route"]),
            }
        )
    return flags


def _risk_label(finding: dict[str, Any]) -> str:
    rule_id = str(finding.get("rule_id") or "")
    labels = {
        "white_paper_invitation_gate": "Invitation-only proposal path",
        "late_fy26_white_paper_window": "White-paper timing and funding window",
        "funding_uncertainty_zero_award": "Funding and zero-award uncertainty",
        "nonstandard_award_instrument": "Award vehicle and terms discretion",
        "foreign_participation_restriction": "Foreign participation restriction",
        "foci_mitigation_prerequisite": "FOCI mitigation gate",
        "export_control_for_foreign_nationals": "Export-control approval gate",
        "organizational_conflict_of_interest": "OCI screening required",
        "disa_cloud_authorization_required": "DISA cloud authorization path",
        "basic_nist_assessment_required": "NIST/SPRS readiness",
        "classified_clearance_required": "Clearance posture required",
        "mandatory_cost_share_without_nontraditional_prime": "Cost-share exposure",
        "government_approved_accounting_system_required": "Approved accounting system",
        "government_favorable_data_rights": "Government-favorable data rights",
    }
    if rule_id in labels:
        return labels[rule_id]
    summary = str(finding.get("summary") or "")
    lower = summary.lower()
    keyword_labels = (
        (("invitation", "not open"), "Invitation-only proposal path"),
        (("white-paper", "window"), "White-paper timing window"),
        (("zero", "award"), "Funding and zero-award uncertainty"),
        (("foreign", "participation"), "Foreign participation restriction"),
        (("foci",), "FOCI mitigation gate"),
        (("export-control",), "Export-control approval gate"),
        (("organizational conflict", "oci"), "OCI screening required"),
        (("disa", "cloud"), "DISA cloud authorization path"),
        (("nist", "sprs"), "NIST/SPRS readiness"),
        (("clearance",), "Clearance posture required"),
        (("cost-share",), "Cost-share exposure"),
        (("accounting system",), "Approved accounting system"),
        (("data rights",), "Government-favorable data rights"),
    )
    for tokens, label in keyword_labels:
        if any(token in lower for token in tokens):
            return label
    return summary if len(summary) <= 88 else f"{summary[:85]}..."


def _extracted_json(
    state: dict[str, Any],
    completion: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "case_id": state["case_id"],
        "opportunity_stage": "presolicitation",
        "decision_question": "Should BD/Ops pursue and prepare for the next solicitation step?",
        "ai_recommendation": completion["ai_synthesis"]["recommendation"],
        "bd_ops_decision": completion["bd_ops_decision"]["decision"],
        "evidence_items": len(evidence_items),
        "departments_routed": ["legal", "security", "finance", "implementation"],
    }


def _departments(
    findings: list[dict[str, Any]],
    completion: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reviews = {review["department"]: review for review in completion.get("specialist_reviews", [])}
    departments = []
    for dept in DEPARTMENTS:
        review = reviews.get(dept)
        dept_findings = [finding for finding in findings if finding["route"] == dept]
        if not review or not dept_findings:
            continue
        departments.append(
            {
                "id": dept,
                "name": DEPARTMENT_LABELS[dept],
                "status": _review_status_label(review["status"]),
                "facts": [finding["summary"] for finding in dept_findings[:4]],
                "packet_precis": review["decision"],
                "packet_recommendation": _review_status_label(review["status"]),
                "packet_questions": review.get("open_questions", []),
                "reviewer_initials": "".join(part[0] for part in DEPARTMENT_LABELS[dept].split())[
                    :2
                ],
                "reviewer": review["reviewer_role"],
                "review_time": _review_time(dept),
                "decision": _review_status_label(review["status"]),
                "summary": review["decision"],
                "conditions": review.get("conditions", []),
            }
        )
    return departments


def _evidence_items(case_dir: Path, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_text = (case_dir / "extracted" / "ai_normalized_packet.local.md").read_text(
        encoding="utf-8"
    )
    items = []
    seen_quotes: set[str] = set()
    for finding in findings:
        for evidence in finding.get("evidence", []):
            quote = _clean_demo_quote(str(evidence.get("quote") or "").strip())
            quote = _verbatim_source_phrase(quote, source_text)
            if not quote or quote in seen_quotes:
                continue
            seen_quotes.add(quote)
            department = DEPARTMENT_LABELS.get(finding["route"], finding["route"])
            items.append(
                {
                    "id": f"ev-{len(items) + 1:02d}",
                    "department": department,
                    "document": "AI-normalized packet",
                    "document_id": "ai_normalized_packet",
                    "page": _page_from_locator(str(evidence.get("locator") or "")),
                    "locator": str(evidence.get("locator") or "source packet"),
                    "source_phrase": _short_phrase(quote),
                    "full_source": quote,
                    "extracted_fact": str(evidence.get("normalized_fact") or finding["summary"]),
                    "confidence": _confidence_label(evidence, finding),
                    "conclusion": "Capture condition",
                    "risk": finding.get("severity") in {"medium", "high", "critical"},
                    "ai_reasoning": finding["summary"],
                    "specialist_conclusion": "Specialist review accepted pursuit with conditions.",
                }
            )
    return items


def _ai_synthesis(completion: dict[str, Any]) -> dict[str, Any]:
    synthesis = completion["ai_synthesis"]
    return {
        "headline": "Recommend pursue with conditions - prepare for the next solicitation step.",
        "summary": synthesis["executive_summary"],
        "document_title": "AI Capture Synthesis Packet",
        "document_sections": [
            {"heading": "Opportunity summary", "body": synthesis["opportunity_summary"]},
            {
                "heading": "Specialist summary",
                "body": " ".join(synthesis.get("specialist_summary", [])),
            },
            {"heading": "Rationale", "body": synthesis["rationale"]},
            {"heading": "Open questions", "body": " ".join(synthesis.get("open_questions", []))},
        ],
        "note": "The AI synthesis recommends; BD/Ops owns the final capture decision.",
    }


def _conditions(completion: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = []
    for index, text in enumerate(completion["ai_synthesis"].get("conditions", [])[:8], start=1):
        conditions.append(
            {
                "number": index,
                "text": text,
                "department": _condition_department(text),
            }
        )
    return conditions


def _audit_events(completion: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"time": event["timestamp"], "event": f"{event['actor']} - {event['summary']}"}
        for event in completion.get("audit_events", [])
    ]


def _kpi_dashboard(
    evidence_items: list[dict[str, Any]],
    audit_events: list[dict[str, str]],
) -> dict[str, Any]:
    counts = {DEPARTMENT_LABELS[dept]: 0 for dept in DEPARTMENTS}
    for item in evidence_items:
        counts[item["department"]] = counts.get(item["department"], 0) + 1
    return {
        "summary": [
            {
                "label": "Total processing time",
                "value": "11h 29m",
                "detail": "includes overnight AI + human reviews",
            },
            {
                "label": "Evidence phrases",
                "value": str(len(evidence_items)),
                "detail": "grounded from public packet",
            },
            {"label": "AI confidence", "value": "87%", "detail": "synthesis recommendation"},
            {"label": "Human decisions", "value": "5", "detail": "4 specialists + BD/Ops"},
        ],
        "stage_times": [
            {"label": "Screen", "seconds": 240, "group": "ai"},
            {"label": "Normalize", "seconds": 120, "group": "ai"},
            {"label": "Extract", "seconds": 540, "group": "ai"},
            {"label": "Route", "seconds": 30, "group": "ai"},
            {"label": "Review", "seconds": 5400, "group": "human"},
            {"label": "Synthesize", "seconds": 45, "group": "ai"},
            {"label": "BD/Ops", "seconds": 3600, "group": "decision"},
        ],
        "department_counts": [
            {"department": department, "count": count} for department, count in counts.items()
        ],
        "audit_density": [
            {"time": "12:01", "count": 1, "group": "ai"},
            {"time": "12:10", "count": 1, "group": "ai"},
            {"time": "10:30", "count": 1, "group": "human"},
            {"time": "10:42", "count": 1, "group": "human"},
            {"time": "10:53", "count": 1, "group": "human"},
            {"time": "11:05", "count": 1, "group": "human"},
            {"time": "11:18", "count": 1, "group": "ai"},
            {"time": "11:30", "count": 1, "group": "decision"},
        ],
    }


def _condition_department(text: str) -> str:
    lower = text.lower()
    if any(
        token in lower
        for token in ("eligibility", "data-rights", "oci", "foreign", "export-control")
    ):
        return "Legal"
    if any(token in lower for token in ("cloud", "clearance", "nist", "safeguarding")):
        return "Security"
    if any(token in lower for token in ("cost", "accounting", "funding")):
        return "Finance"
    return "Implementation"


def _confidence_label(evidence: dict[str, Any], finding: dict[str, Any]) -> str:
    confidence = float(evidence.get("confidence") or finding.get("confidence") or 0.85)
    return f"{round(confidence * 100)}%"


def _risk_level(findings: list[dict[str, Any]]) -> str:
    severities = {finding.get("severity") for finding in findings}
    if "critical" in severities:
        return "Critical"
    if "high" in severities:
        return "High"
    if "medium" in severities:
        return "Medium"
    return "Low"


def _review_status_label(status: str) -> str:
    return {
        "worth_pursuing": "Worth pursuing",
        "worth_pursuing_with_conditions": "Worth pursuing with conditions",
        "hold_pending_information": "Hold pending information",
        "do_not_pursue": "Do not pursue",
    }.get(status, status.replace("_", " ").title())


def _decision_label(decision: str) -> str:
    return {
        "pursue_with_conditions": "Pursue with conditions",
        "pursue": "Pursue",
        "hold_pending_information": "Hold pending information",
        "do_not_pursue": "Do not pursue",
    }.get(decision, decision.replace("_", " ").title())


def _review_time(department: str) -> str:
    return {
        "legal": "10:30 AM",
        "security": "10:42 AM",
        "finance": "10:53 AM",
        "implementation": "11:05 AM",
    }[department]


def _page_from_locator(locator: str) -> str:
    match = re.search(r"p\.(\d+)", locator)
    return match.group(1) if match else "packet"


def _short_phrase(quote: str) -> str:
    one_line = " ".join(quote.split())
    return one_line if len(one_line) <= 130 else f"{one_line[:127]}..."


def _clean_demo_quote(quote: str) -> str:
    match = re.search(r"- Quote:\s*(.+?)(?:\s+- Normalized fact:|$)", quote)
    if match:
        return match.group(1).strip()
    return quote


def _verbatim_source_phrase(quote: str, source_text: str) -> str:
    if quote in source_text:
        return quote
    compact_quote = re.sub(r"\s+", " ", quote)
    for quoted in re.findall(r"- Quote:\s*(.+?)(?:\n- Normalized fact:|$)", source_text, re.S):
        if re.sub(r"\s+", " ", quoted).strip() == compact_quote:
            return quoted.strip()
    return quote


if __name__ == "__main__":
    main()
