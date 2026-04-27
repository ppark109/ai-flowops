from __future__ import annotations

import json
from pathlib import Path

from schemas.case import DocumentRef
from schemas.guided_demo import DemoCaseSpec

GUIDED_DEMO_CASE_PATH = Path("data/guided_demo/flagship_case.json")
GUIDED_DEMO_STEPS = [
    {
        "id": "documents",
        "label": "Documents Received",
        "short_label": "What came in?",
        "badge": "Automated",
        "description": "RFP materials are received and normalized into a case record.",
        "why": "This shows the system starts from messy business documents, not a hand-entered form.",
    },
    {
        "id": "extraction",
        "label": "Text Extracted",
        "short_label": "What did AI extract?",
        "badge": "Automated",
        "description": "Key facts and source evidence are extracted from unstructured documents.",
        "why": "This is the first AI value: turning documents into structured operational facts.",
    },
    {
        "id": "ai-decision",
        "label": "AI Decision Generated",
        "short_label": "What did AI recommend?",
        "badge": "AI-assisted",
        "description": "AI recommends a conditional bid and explains the evidence.",
        "why": "The AI gives a business recommendation with evidence, not a vague summary.",
    },
    {
        "id": "routing",
        "label": "Department Packets Created",
        "short_label": "Why route departments?",
        "badge": "Workflow",
        "description": "The workflow creates specialist packets for each review lane.",
        "why": "The system splits one intake into parallel expert work so no team reviews irrelevant material.",
    },
    {
        "id": "human-review",
        "label": "Human Review Completed",
        "short_label": "What did humans decide?",
        "badge": "Human-in-the-loop",
        "description": "Reviewers approve with conditions or request missing information.",
        "why": "Humans remain accountable for legal, security, finance, and delivery commitments.",
    },
    {
        "id": "final-decision",
        "label": "Final Decision Logged",
        "short_label": "What did BD/Ops do?",
        "badge": "Governed",
        "description": "AI synthesis is presented to BD/Ops for the final business decision.",
        "why": "The final decision is owned by BD/Ops after AI synthesizes specialist conclusions.",
    },
    {
        "id": "kpis",
        "label": "KPIs Updated",
        "short_label": "What value did it create?",
        "badge": "Analytics",
        "description": "Operational metrics and workflow outcomes are captured for review.",
        "why": (
            "This turns AI work into measurable operations outcomes: routed packets, "
            "reviews, overrides, and time saved."
        ),
    },
]


def load_guided_demo_case(path: Path = GUIDED_DEMO_CASE_PATH) -> DemoCaseSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["source_documents"] = _hydrate_source_documents(raw.get("source_documents", []), path)
    return DemoCaseSpec.model_validate(raw)


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
    for evidence in case.expected_evidence:
        document = next(
            (
                item
                for item in case.source_documents
                if item.document_type == evidence.source_document
            ),
            None,
        )
        if document is None or document.content is None:
            raise ValueError(f"Missing guided-demo source document: {evidence.source_document}")
        if evidence.source_phrase not in document.content:
            raise ValueError(f"Evidence phrase missing from source document: {evidence.evidence_id}")


def _hydrate_source_documents(documents: list[dict[str, object]], case_path: Path) -> list[dict[str, object]]:
    hydrated_documents = []
    for item in documents:
        document = DocumentRef.model_validate(item)
        if document.path is None:
            hydrated_documents.append(document.model_dump())
            continue
        doc_path = _resolve_demo_document_path(document.path, case_path)
        hydrated_documents.append(
            document.model_copy(update={"content": doc_path.read_text(encoding="utf-8")}).model_dump()
        )
    return hydrated_documents


def _resolve_demo_document_path(path: str, case_path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = case_path.parent / candidate
    resolved = candidate.resolve()
    data_root = Path("data").resolve()
    if not resolved.is_relative_to(data_root):
        raise ValueError(f"Guided-demo source document must be under data/: {path}")
    if not resolved.is_file():
        raise FileNotFoundError(path)
    return resolved


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
        "active_step_record": next(
            step for step in GUIDED_DEMO_STEPS if step["id"] == active_step
        ),
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
        "executive_summary": _executive_summary(case),
    }


def _executive_summary(case: DemoCaseSpec) -> list[tuple[str, str]]:
    return [
        ("Business problem", "A state government RFP arrives; BD/Ops needs to know whether to bid."),
        ("AI recommendation", f"{case.ai_recommendation}: route to specialists before committing proposal work."),
        ("Departments routed", "Legal, Security, Finance, and Implementation."),
        ("Human review result", "Specialists approved qualification with required conditions and follow-up."),
        ("BD/Ops decision", case.final_decision),
        ("Time/value impact", "One guided workflow creates review packets, evidence traceability, and KPI records."),
    ]


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
    source_order = [document.document_type for document in case.source_documents]
    for doc_type in by_document:
        if doc_type not in source_order:
            source_order.append(doc_type)
    by_doc_type = {document.document_type: document for document in case.source_documents}
    return [
        {
            "document_type": doc_type,
            "title": titles.get(doc_type, doc_type.replace("_", " ").title()),
            "page_label": f"Page {index} of 5",
            "summary": _document_summary(doc_type, case),
            "content": by_doc_type.get(doc_type).content if doc_type in by_doc_type else "",
            "highlights": by_document.get(doc_type, []),
        }
        for index, doc_type in enumerate(source_order, start=1)
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
