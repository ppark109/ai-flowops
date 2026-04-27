from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.guided_demo import resolve_evidence_references
from app.main import create_app
from schemas.case import IntakePackage
from scripts.prepare_guided_demo_ai import validate_candidate
from workflows.orchestrator import WorkflowOrchestrator
from workflows.playbook import load_default_playbook
from workflows.storage import WorkflowStorage


def _client() -> TestClient:
    return TestClient(create_app())


def test_home_and_demo_render_case_room_hero() -> None:
    client = _client()

    for path in ("/", "/demo"):
        response = client.get(path)

        assert response.status_code == 200
        assert "A $4.8M government RFP arrived. Should we bid?" in response.text
        assert "Overnight AI screening selected this RFP" in response.text
        assert "opportunities screened" in response.text
        assert "Promoted this RFP" in response.text or "promoted this RFP" in response.text
        assert "Walk through the case" in response.text
        assert "/demo/cases/demo-gov-benefits-001?step=received" in response.text
        assert "Read-only guided demo of a completed AI-processed workflow." in response.text


def test_demo_cases_no_longer_lists_smaller_examples() -> None:
    client = _client()

    response = client.get("/demo/cases")

    assert response.status_code == 200
    assert "State Benefits Portal Modernization" in response.text
    assert "Customer Escalation Email" not in response.text
    assert "Vendor Procurement Request" not in response.text


def test_case_walkthrough_renders_left_rail_and_extraction_stage() -> None:
    client = _client()

    response = client.get("/demo/cases/demo-gov-benefits-001?step=extraction")

    assert response.status_code == 200
    assert "Document received" in response.text
    assert "AI extraction" in response.text
    assert "BD/Ops decision" in response.text
    assert "What did AI read from the RFP?" in response.text
    assert "No stated liability cap" in response.text
    assert "Source evidence phrases (11)" in response.text
    assert "23 structured facts" in response.text


def test_recommendation_and_routing_show_ai_banner_and_all_departments() -> None:
    client = _client()

    response = client.get("/demo/cases/demo-gov-benefits-001?step=recommendation")

    assert response.status_code == 200
    assert "Conditional bid - pursue with 4 conditions resolved" in response.text
    assert "Legal" in response.text
    assert "Security" in response.text
    assert "Finance" in response.text
    assert "Implementation" in response.text
    assert "What the AI did" in response.text
    assert "It mapped extracted facts to specialist ownership" in response.text
    assert "Show packet contents and routing logic" not in response.text


def test_document_received_shows_overnight_screening_context() -> None:
    client = _client()

    response = client.get("/demo/cases/demo-gov-benefits-001?step=received")

    assert response.status_code == 200
    assert "Overnight opportunity screening" in response.text
    assert "43 opportunities downloaded" in response.text
    assert "42 low-fit notices filtered" in response.text
    assert "1 opportunity promoted" in response.text
    assert "Promote for bid/no-bid analysis" in response.text


def test_outcome_view_shows_conditions_and_kpi_summary() -> None:
    client = _client()

    response = client.get("/demo/cases/demo-gov-benefits-001?step=decision")

    assert response.status_code == 200
    assert "BID - conditional" in response.text
    assert "Negotiate liability cap before contract execution" in response.text
    assert "Obtain signed DPA and confirm data residency" in response.text
    assert "Re-price fixed-fee with mainframe risk contingency" in response.text
    assert "Confirm staff availability for 12-week schedule" in response.text
    assert "~2.3d" in response.text


def test_proof_routes_render() -> None:
    client = _client()

    paths = (
        "/demo/evidence-map",
        "/demo/source-document",
        "/demo/department-packet",
        "/demo/document-package",
        "/demo/document/rfp",
        "/demo/kpis",
        "/demo/architecture",
    )
    for path in paths:
        response = client.get(path)

        assert response.status_code == 200
        assert "State Benefits Portal" in response.text


def test_public_demo_pages_do_not_expose_mutating_controls() -> None:
    client = _client()
    paths = (
        "/",
        "/demo",
        "/demo/cases/demo-gov-benefits-001?step=extraction",
        "/demo/cases/demo-gov-benefits-001?step=decision",
        "/demo/evidence-map",
        "/demo/source-document",
        "/demo/department-packet",
        "/demo/document-package",
        "/demo/document/rfp",
        "/demo/kpis",
        "/demo/architecture",
    )

    for path in paths:
        response = client.get(path)

        assert response.status_code == 200
        assert "<form" not in response.text
        assert 'method="post"' not in response.text.lower()
        assert "/api/cases" not in response.text
        assert "/api/approvals" not in response.text
        assert "admin token" not in response.text.lower()


def test_evidence_references_resolve_to_source_phrases() -> None:
    assert resolve_evidence_references()


def test_document_package_links_to_actual_source_documents() -> None:
    client = _client()

    response = client.get("/demo/document-package")

    assert response.status_code == 200
    assert "Initial document package" in response.text
    assert "/demo/document/intake_email" in response.text
    assert "/demo/document/rfp" in response.text
    assert "/demo/document/pricing_exhibit" in response.text
    assert "/demo/document/implementation_exhibit" in response.text
    assert "/demo/document/security_questionnaire" in response.text


def test_department_packet_reads_like_handoff_memo_with_verifiable_quotes() -> None:
    client = _client()

    response = client.get("/demo/department-packet?department=legal")

    assert response.status_code == 200
    assert "AI-generated handoff memo" in response.text
    assert "Recommended specialist action" in response.text
    assert "Questions for Legal" in response.text
    assert "Verification references" in response.text
    assert "Request for Proposal, p. 10" in response.text
    assert "View highlighted phrase" in response.text
    assert "Specialist conclusion" not in response.text


def test_source_documents_are_fuller_than_single_evidence_bullets() -> None:
    client = _client()

    response = client.get("/demo/document/rfp")

    assert response.status_code == 200
    assert "Page 1 - Cover and Procurement Notice" in response.text
    assert "Page 12 - Submission Instructions" in response.text
    assert "The RFP does not state a separate monetary liability cap" in response.text


def test_ai_synthesis_is_full_bd_ops_document() -> None:
    client = _client()

    response = client.get("/demo/cases/demo-gov-benefits-001?step=synthesis")

    assert response.status_code == 200
    assert "AI synthesis packet for BD/Ops" in response.text
    assert "RFP summary" in response.text
    assert "Decision request for BD/Ops" in response.text


def test_kpi_dashboard_includes_screening_savings() -> None:
    client = _client()

    response = client.get("/demo/kpis")

    assert response.status_code == 200
    assert "Opportunity screening saved" in response.text
    assert "4h" in response.text
    assert "Total estimated time saved" in response.text
    assert "Screen" in response.text
    assert "Download" in response.text
    assert "Normalize" in response.text
    assert "Enrich" in response.text
    assert "density-ai" in response.text
    assert "density-human" in response.text
    assert "density-decision" in response.text
    assert 'href="#audit-bucket-0001"' in response.text
    assert 'id="audit-bucket-0001"' in response.text
    assert "Opportunity API scan started" in response.text
    assert "Security review returned" in response.text
    assert 'id="audit-bucket-1028"' in response.text
    assert "AI synthesis generated" in response.text
    assert 'id="audit-bucket-1031"' in response.text
    assert "BD/Ops decision logged" in response.text


def test_case_timestamps_match_midnight_ai_and_business_hour_reviews() -> None:
    client = _client()

    extraction = client.get("/demo/cases/demo-gov-benefits-001?step=extraction")
    reviews = client.get("/demo/cases/demo-gov-benefits-001?step=reviews")
    decision = client.get("/demo/cases/demo-gov-benefits-001?step=decision")

    assert extraction.status_code == 200
    assert reviews.status_code == 200
    assert decision.status_code == 200
    assert "12:10 AM" in extraction.text
    assert "10:30 AM" in reviews.text
    assert "11:30 AM" in decision.text


def test_codex_candidate_validator_requires_grounded_screening_reasons() -> None:
    documents = {
        "rfp": "The current benefits portal was introduced more than a decade ago.",
        "pricing_exhibit": "The modernization program will be contracted as a fixed fee.",
    }
    candidate = {
        "screening": {
            "recommendation": "Promote for bid/no-bid analysis",
            "confidence": 0.88,
            "source_reasons": [
                {
                    "document_id": "rfp",
                    "quote": "The current benefits portal was introduced more than a decade ago.",
                    "reason": "Modernization work matches target services.",
                }
            ],
        },
        "case_analysis": {
            "recommendation": "conditional bid",
            "confidence": 0.91,
            "risk_flags": [],
            "department_packets": [
                {
                    "department": "Finance",
                    "precis": "Fixed-fee scope should be reviewed.",
                    "recommendation": "Model margin risk.",
                    "supporting_facts": [
                        {
                            "fact": "Fixed-fee structure",
                            "document_id": "pricing_exhibit",
                            "quote": "The modernization program will be contracted as a fixed fee.",
                        }
                    ],
                    "questions": ["What contingency is required?"],
                }
            ],
            "ai_synthesis": {
                "headline": "Recommend conditional bid",
                "summary": "Proceed if conditions are addressed.",
                "conditions": ["Model fixed-fee risk"],
            },
        },
    }

    validate_candidate(candidate, documents)


def test_full_document_package_runtime_findings_stay_grounded_by_department() -> None:
    documents = Path("data/guided_demo/documents")
    case = IntakePackage(
        case_id="demo-gov-benefits-001-runtime-test",
        customer_name="Department of Social Services",
        account_name="State Benefits Portal Modernization",
        intake_email_text=(documents / "intake_email.md").read_text(encoding="utf-8"),
        contract_text=(documents / "rfp.md").read_text(encoding="utf-8"),
        order_form_text=(documents / "pricing_exhibit.md").read_text(encoding="utf-8"),
        implementation_notes=(documents / "implementation_exhibit.md").read_text(
            encoding="utf-8"
        ),
        security_questionnaire_text=(
            documents / "security_questionnaire.md"
        ).read_text(encoding="utf-8"),
        metadata={"source": "guided_demo_runtime_test"},
    )

    with TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(str(Path(temp_dir) / "runtime-test.sqlite3"))
        storage.upsert_case(case, state="draft")
        result = WorkflowOrchestrator(storage, load_default_playbook()).run_case(case)

    assert result.state == "awaiting_approval"
    assert result.routing_decision
    assert result.routing_decision.recommended_route == "legal"
    assert result.routing_decision.approval_required is True

    assert result.normalized_case
    assert "fixed_fee_scope_risk" in result.normalized_case.risk_signals
    assert "implementation_dependency_risk" in result.normalized_case.risk_signals
    assert "incomplete_intake_package" not in result.normalized_case.risk_signals
    assert "clean_standard_package" not in {finding.rule_id for finding in result.findings}

    route_sources = {
        finding.route: {
            span.source_document_type
            for finding_for_route in result.findings
            if finding_for_route.route == finding.route
            for span in finding_for_route.evidence
        }
        for finding in result.findings
    }
    assert "contract" in route_sources["legal"]
    assert "security_questionnaire" in route_sources["security"]
    assert "order_form" in route_sources["finance"]
    assert "implementation" in route_sources["implementation"]
