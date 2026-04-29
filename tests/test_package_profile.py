from pathlib import Path

from schemas.case import EvidenceSpan, Finding
from scripts.prepare_real_case import _build_ai_normalized_packet
from workflows.package_profile import build_package_profile


def _document(
    file: str,
    *,
    role: str = "program_solicitation",
    chars: int = 1_000,
    pages: int = 3,
) -> dict:
    return {
        "file": file,
        "role": role,
        "description": "",
        "text": "x" * chars,
        "text_path": f"extracted/{Path(file).stem}.md",
        "page_count": pages,
        "sha256": "abc123",
    }


def test_small_package_selects_simple_direct_ai() -> None:
    profile = build_package_profile(
        manifest={},
        documents=[_document("notice.pdf", chars=2_000, pages=4)],
    )

    assert profile["processing_mode"] == "simple_direct_ai"
    assert profile["trigger_reasons"] == []


def test_large_package_selects_normalized_packet_path() -> None:
    profile = build_package_profile(
        manifest={},
        documents=[
            _document("main-rfp.pdf", chars=65_000, pages=78),
            _document("amendment-1.pdf", role="amendment_or_update", chars=2_000, pages=2),
        ],
    )

    assert profile["processing_mode"] == "large_normalized_packet"
    assert "total_pages_gt_75" in profile["trigger_reasons"]
    assert "total_chars_gt_threshold" in profile["trigger_reasons"]
    assert "largest_document_chars_gt_40000" in profile["trigger_reasons"]
    assert "amendment_or_update_detected" in profile["trigger_reasons"]


def test_processing_mode_overrides_force_expected_path() -> None:
    large_docs = [_document("main-rfp.pdf", chars=90_000, pages=100)]

    forced_simple = build_package_profile(
        manifest={},
        documents=large_docs,
        requested_mode="simple",
    )
    forced_large = build_package_profile(
        manifest={},
        documents=[_document("notice.pdf", chars=2_000, pages=3)],
        requested_mode="large",
    )
    manifest_large = build_package_profile(
        manifest={"processing_mode": "large"},
        documents=[_document("notice.pdf", chars=2_000, pages=3)],
    )

    assert forced_simple["processing_mode"] == "simple_direct_ai"
    assert forced_large["processing_mode"] == "large_normalized_packet"
    assert forced_large["trigger_reasons"] == ["forced_by_cli_large"]
    assert manifest_large["trigger_reasons"] == ["forced_by_manifest_large"]


def test_chunk_reviews_preserve_source_file_page_and_quote(monkeypatch, tmp_path) -> None:
    class FakeAgent:
        def __init__(self, **_kwargs):
            pass

        def run(self, _intake):
            evidence = [
                EvidenceSpan(
                    source_document_type="program_solicitation",
                    locator="page 1",
                    quote="The offeror must submit a technical volume.",
                    normalized_fact="Technical volume required.",
                    confidence=0.91,
                )
            ]
            finding = Finding(
                finding_id="chunk-test-ai-01",
                rule_id="technical_volume_required",
                finding_type="ai_review",
                severity="medium",
                route="implementation",
                summary="Technical volume requires implementation review.",
                evidence=evidence,
                confidence=0.89,
                source_agent="CodexReviewAgent",
            )
            return evidence, [finding], None

    monkeypatch.setattr("agents.openai_review.CodexReviewAgent", FakeAgent)
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "extracted").mkdir()
    document_text = (
        "# Extracted text: main-rfp.pdf\n\n"
        "## Page 1\nThe offeror must submit a technical volume.\n\n"
        "## Page 2\nNo additional issue."
    )

    result = _build_ai_normalized_packet(
        case_dir=case_dir,
        case_id="CASE-001",
        customer_name="Agency",
        account_name="Opportunity",
        documents=[
            {
                "file": "main-rfp.pdf",
                "role": "program_solicitation",
                "description": "",
                "text": document_text,
                "text_path": str(case_dir / "extracted" / "main-rfp.md"),
                "page_count": 2,
                "sha256": "abc123",
            }
        ],
        codex_command="codex",
        codex_model="gpt-5.4",
        timeout_seconds=60,
        chunk_chars=2_000,
        max_chunks=0,
        opportunity_stage="final_solicitation",
        processing_profile={
            "processing_mode": "large_normalized_packet",
            "complexity_score": 88,
            "trigger_reasons": ["total_chars_gt_threshold"],
        },
    )

    packet_text = Path(result["text_path"]).read_text(encoding="utf-8")
    chunk_reviews = Path(result["chunk_reviews_path"]).read_text(encoding="utf-8")

    assert "chunk-001 / main-rfp.pdf pages 1-2 / page 1" in packet_text
    assert "The offeror must submit a technical volume." in packet_text
    assert '"source_file": "main-rfp.pdf"' in chunk_reviews
    assert '"pages": "1-2"' in chunk_reviews
    assert '"quote": "The offeror must submit a technical volume."' in chunk_reviews
