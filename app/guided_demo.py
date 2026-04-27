from __future__ import annotations

import json
from pathlib import Path

from schemas.guided_demo import DemoCaseSpec

GUIDED_DEMO_CASE_PATH = Path("data/guided_demo/flagship_case.json")
GUIDED_DEMO_STEPS = [
    {
        "id": "documents",
        "label": "Documents Received",
        "short_label": "Input Documents",
        "badge": "Automated",
        "description": "RFP materials are received and normalized into a case record.",
    },
    {
        "id": "extraction",
        "label": "Text Extracted",
        "short_label": "Text Extracted",
        "badge": "Automated",
        "description": "Key facts and source evidence are extracted from unstructured documents.",
    },
    {
        "id": "ai-decision",
        "label": "AI Decision Generated",
        "short_label": "AI Decision",
        "badge": "AI-assisted",
        "description": "AI recommends a conditional bid and explains the evidence.",
    },
    {
        "id": "routing",
        "label": "Department Packets Created",
        "short_label": "Department Routing",
        "badge": "Workflow",
        "description": "The workflow creates specialist packets for each review lane.",
    },
    {
        "id": "human-review",
        "label": "Human Review Completed",
        "short_label": "Human Review",
        "badge": "Human-in-the-loop",
        "description": "Reviewers approve with conditions or request missing information.",
    },
    {
        "id": "final-decision",
        "label": "Final Decision Logged",
        "short_label": "Final Decision",
        "badge": "Governed",
        "description": "AI synthesis is presented to BD/Ops for the final business decision.",
    },
    {
        "id": "kpis",
        "label": "KPIs Updated",
        "short_label": "KPI Dashboard",
        "badge": "Analytics",
        "description": "Operational metrics and workflow outcomes are captured for review.",
    },
]


def load_guided_demo_case(path: Path = GUIDED_DEMO_CASE_PATH) -> DemoCaseSpec:
    return DemoCaseSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))


def validate_guided_demo_case(case: DemoCaseSpec) -> None:
    evidence_ids = set(case.evidence_by_id)
    missing = sorted(case.referenced_evidence_ids() - evidence_ids)
    if missing:
        raise ValueError(f"Unknown guided-demo evidence ids: {', '.join(missing)}")

    packet_departments = {packet.department for packet in case.department_packets}
    conclusion_departments = {item.department for item in case.specialist_conclusions}
    if packet_departments != conclusion_departments:
        raise ValueError("Guided-demo packet departments and conclusion departments must match.")
    if not case.evidence_map:
        raise ValueError("Guided-demo case must include an evidence map.")
    if not case.audit_events:
        raise ValueError("Guided-demo case must include audit events.")


def guided_demo_view_model(active_step: str = "documents", active_tab: str = "source") -> dict[str, object]:
    case = load_guided_demo_case()
    validate_guided_demo_case(case)
    step_ids = {step["id"] for step in GUIDED_DEMO_STEPS}
    tab_ids = {"source", "extracted", "metadata"}
    if active_step not in step_ids:
        active_step = "documents"
    if active_tab not in tab_ids:
        active_tab = "source"

    return {
        "demo_case": case,
        "steps": GUIDED_DEMO_STEPS,
        "active_step": active_step,
        "active_tab": active_tab,
        "overview_flow": [
            step for step in GUIDED_DEMO_STEPS if step["id"] != "extraction"
        ],
        "documents": _document_previews(case),
        "extracted_fields": _extracted_fields(case),
        "metadata_rows": _metadata_rows(case),
        "kpi_cards": _kpi_cards(),
        "charts": _chart_cards(),
        "read_only_notice": (
            "Read-only precomputed demo. Public viewers cannot run AI, reset data, "
            "import/export bundles, or mutate workflow records from these pages."
        ),
    }


def _document_previews(case: DemoCaseSpec) -> list[dict[str, object]]:
    by_document: dict[str, list[str]] = {}
    for evidence in case.expected_evidence:
        by_document.setdefault(evidence.source_document, []).append(evidence.source_phrase)

    titles = {
        "intake_email": "Intake Email",
        "contract": "Draft Contract Terms",
        "order_form": "Pricing and Order Form",
        "implementation_notes": "Implementation Notes",
        "security_questionnaire": "Security Questionnaire",
    }
    return [
        {
            "document_type": doc_type,
            "title": titles.get(doc_type, doc_type.replace("_", " ").title()),
            "page_label": f"Page {index} of 5",
            "summary": _document_summary(doc_type, case),
            "highlights": phrases,
        }
        for index, (doc_type, phrases) in enumerate(by_document.items(), start=1)
    ]


def _document_summary(doc_type: str, case: DemoCaseSpec) -> str:
    summaries = {
        "contract": "State terms include legal exposure that must be reviewed before proposal commitment.",
        "security_questionnaire": "Security materials identify regulated data and missing privacy documentation.",
        "order_form": (
            f"The commercial packet frames a ${case.estimated_value_usd:,} opportunity "
            "with pricing obligations."
        ),
        "implementation_notes": "Delivery notes describe a compressed launch and legacy integration dependency.",
        "intake_email": "The account team requests a qualification decision before proposal work begins.",
    }
    return summaries.get(doc_type, case.summary)


def _extracted_fields(case: DemoCaseSpec) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "workflow_type": case.workflow_type,
        "agency": case.customer_agency,
        "estimated_value": case.estimated_value_usd,
        "deadline": case.response_deadline,
        "ai_recommendation": case.ai_recommendation,
        "primary_route": case.primary_route,
        "supporting_routes": case.supporting_routes,
        "requires_legal_review": True,
        "requires_security_review": True,
        "requires_finance_review": True,
        "requires_implementation_review": True,
        "final_decision_owner": case.decision_owner,
    }


def _metadata_rows(case: DemoCaseSpec) -> list[tuple[str, str]]:
    return [
        ("Received", "Apr 25, 2026, 10:14 AM"),
        ("Input type", case.input_type),
        ("Extraction status", "Complete"),
        ("Linked workflow", case.workflow_type),
        ("Demo mode", "Precomputed read-only case"),
    ]


def _kpi_cards() -> list[tuple[str, str]]:
    return [
        ("Documents Processed", "24"),
        ("Cases Routed", "11"),
        ("Department Packets Created", "38"),
        ("Human Reviews Completed", "31"),
        ("AI Recommendations Accepted", "82%"),
        ("Human Overrides", "18%"),
        ("Average Processing Time", "7m 42s"),
        ("Estimated Time Saved", "14.5 hours"),
    ]


def _chart_cards() -> list[dict[str, object]]:
    return [
        {
            "title": "Cases by workflow type",
            "rows": [
                ("Contract Intake", 8),
                ("Customer Escalation", 6),
                ("Procurement Request", 5),
                ("Compliance Review", 3),
                ("Vendor Review", 2),
            ],
        },
        {
            "title": "Department workload",
            "rows": [
                ("Legal", 12),
                ("Finance", 9),
                ("Security", 8),
                ("Implementation", 6),
                ("BD/Ops", 4),
            ],
        },
        {
            "title": "AI decision outcomes",
            "rows": [
                ("Proceed", 9),
                ("Conditional Proceed", 7),
                ("Needs More Info", 5),
                ("Do Not Proceed", 3),
            ],
        },
        {
            "title": "Human override rate",
            "rows": [
                ("Accepted as-is", 82),
                ("Modified", 13),
                ("Rejected", 5),
            ],
        },
    ]
