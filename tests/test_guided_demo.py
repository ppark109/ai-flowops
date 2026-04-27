from fastapi.testclient import TestClient

from app.guided_demo import load_guided_demo_case, validate_guided_demo_case
from app.main import create_app


def test_guided_demo_case_has_specialist_packets_and_bd_ops_decision() -> None:
    case = load_guided_demo_case()
    validate_guided_demo_case(case)

    assert case.case_id == "demo-gov-benefits-001"
    assert len(case.source_documents) == 5
    assert all(document.content for document in case.source_documents)
    assert case.primary_route == "legal"
    assert case.decision_owner == "BD/Ops"
    assert case.expected_bd_ops_decision.decision_owner == "BD/Ops"
    assert {packet.department for packet in case.department_packets} == {
        "Legal",
        "Security",
        "Finance",
        "Implementation",
    }
    assert {item.department for item in case.specialist_conclusions} == {
        "Legal",
        "Security",
        "Finance",
        "Implementation",
    }
    assert case.ai_synthesis is not None
    assert case.ai_synthesis.recommendation == "Proceed to qualification with conditions"


def test_guided_demo_evidence_references_are_resolvable() -> None:
    case = load_guided_demo_case()
    evidence_ids = set(case.evidence_by_id)
    documents_by_type = {document.document_type: document for document in case.source_documents}

    assert case.referenced_evidence_ids()
    assert case.referenced_evidence_ids() <= evidence_ids
    assert len(case.evidence_map) == len(case.expected_evidence)
    assert {row.evidence_id for row in case.evidence_map} == evidence_ids
    assert case.audit_events
    assert case.audit_events[-1].event_type == "kpi.updated"
    for evidence in case.expected_evidence:
        document = documents_by_type[evidence.source_document]
        assert document.content is not None
        assert evidence.source_phrase in document.content


def test_guided_demo_public_pages_render() -> None:
    client = TestClient(create_app())
    case = load_guided_demo_case()

    for path in [
        "/",
        "/demo",
        "/demo/cases",
        f"/demo/cases/{case.case_id}",
        f"/demo/cases/{case.case_id}?step=ai-decision",
        f"/demo/cases/{case.case_id}?step=routing",
        f"/demo/cases/{case.case_id}?step=human-review",
        f"/demo/cases/{case.case_id}?step=final-decision",
        f"/demo/cases/{case.case_id}?step=kpis",
        "/demo/architecture",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "State Benefits Portal Modernization RFP" in response.text or "How the system is built" in response.text


def test_public_home_leads_with_plain_english_flagship_story() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "A government RFP arrives. Should we bid?" in response.text
    assert "AI recommends conditional bid; BD/Ops proceeds with four conditions." in response.text
    assert "Business problem" in response.text
    assert "Final BD/Ops decision" not in response.text


def test_guided_demo_gallery_only_shows_flagship_case() -> None:
    client = TestClient(create_app())

    response = client.get("/demo/cases")

    assert response.status_code == 200
    assert "State Benefits Portal Modernization RFP" in response.text
    assert "Customer Escalation Email" not in response.text
    assert "Vendor Procurement Request" not in response.text


def test_guided_demo_unknown_case_returns_404() -> None:
    client = TestClient(create_app())

    response = client.get("/demo/cases/not-a-real-case")

    assert response.status_code == 404


def test_guided_demo_pages_do_not_expose_mutating_controls() -> None:
    client = TestClient(create_app())
    case = load_guided_demo_case()
    forbidden_fragments = [
        "<form",
        "method=\"post\"",
        "/run",
        "/api/cases",
        "/api/approvals",
        "/api/evals/run",
        "admin_token",
    ]

    for path in [
        "/",
        "/demo",
        "/demo/cases",
        f"/demo/cases/{case.case_id}",
        "/demo/architecture",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        page = response.text.lower()
        assert "read-only precomputed demo" in page
        for fragment in forbidden_fragments:
            assert fragment not in page


def test_guided_case_keeps_deeper_proof_under_collapsible_sections() -> None:
    client = TestClient(create_app())
    case = load_guided_demo_case()

    response = client.get(f"/demo/cases/{case.case_id}?step=ai-decision")

    assert response.status_code == 200
    assert "Show proof: evidence table and evidence map" in response.text
    assert "Evidence Map" in response.text
    assert "Why this matters" in response.text
