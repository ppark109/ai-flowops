from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def _ensure_project_root() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> None:
    _ensure_project_root()

    from app.settings import get_settings
    from schemas.case import DocumentRef, IntakePackage
    from workflows.orchestrator import WorkflowOrchestrator
    from workflows.package_profile import build_package_profile

    parser = argparse.ArgumentParser(
        description=(
            "Extract and process a local government document package through "
            "the AI FlowOps Codex review path."
        )
    )
    parser.add_argument("case_dir", type=Path, help="Folder containing real-case PDFs.")
    parser.add_argument("--case-id", help="Override case id. Defaults to folder name.")
    parser.add_argument("--customer-name", default="Government agency", help="Customer/agency label.")
    parser.add_argument("--account-name", help="Opportunity/account label.")
    parser.add_argument(
        "--opportunity-stage",
        choices=("auto", "presolicitation", "final_solicitation"),
        default="auto",
        help=(
            "How Codex should frame the opportunity. Use presolicitation for pre-bid "
            "notices/synopses where the decision is pursuit readiness, not final bid readiness."
        ),
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only create/update manifest and extracted text; do not run Codex or write to DB.",
    )
    parser.add_argument(
        "--processing-mode",
        choices=("auto", "simple", "large"),
        default="auto",
        help=(
            "Opportunity package processing path. auto profiles the package; simple forces "
            "direct AI review; large forces chunked normalized-packet processing."
        ),
    )
    parser.add_argument(
        "--digest-threshold-chars",
        type=int,
        default=60_000,
        help=(
            "If extracted text is larger than this, first create an AI-normalized "
            "packet from page chunks. Use 0 to disable digesting."
        ),
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=6_000,
        help="Approximate max characters per AI chunk during digest creation.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="Debug limit for AI digest chunks. 0 processes all chunks.",
    )
    parser.add_argument(
        "--database-path",
        help="SQLite path. Defaults to app settings DATABASE_PATH.",
    )
    parser.add_argument("--codex-command", help="Codex executable. Defaults to app settings.")
    parser.add_argument("--codex-model", help="Codex model. Defaults to app settings.")
    parser.add_argument(
        "--codex-timeout-seconds",
        type=int,
        help="Codex timeout. Defaults to app settings.",
    )
    args = parser.parse_args()

    case_dir = args.case_dir.resolve()
    if not case_dir.is_dir():
        raise SystemExit(f"Case folder not found: {case_dir}")

    case_id = args.case_id or case_dir.name
    account_name = args.account_name or case_id
    settings = get_settings()
    manifest = _load_or_create_manifest(case_dir, case_id, args.customer_name, account_name)
    extracted_documents = _extract_documents(case_dir, manifest)
    opportunity_stage = _resolve_opportunity_stage(
        requested_stage=args.opportunity_stage,
        manifest=manifest,
        documents=extracted_documents,
    )
    manifest["opportunity_stage"] = opportunity_stage
    profile = build_package_profile(
        manifest=manifest,
        documents=extracted_documents,
        requested_mode=args.processing_mode,
        total_char_threshold=args.digest_threshold_chars,
    )
    manifest["processing_mode"] = profile["processing_mode"]
    _write_manifest(case_dir, manifest)
    _write_processing_artifacts(case_dir, manifest, extracted_documents, profile)

    print(f"case_dir={case_dir}")
    print(f"manifest={case_dir / 'manifest.local.json'}")
    print(f"opportunity_stage={opportunity_stage}")
    print(f"processing_mode={profile['processing_mode']}")
    print(f"complexity_score={profile['complexity_score']}")
    print(f"trigger_reasons={','.join(profile['trigger_reasons']) or 'none'}")
    print(f"extracted={len(extracted_documents)}")
    for document in extracted_documents:
        print(
            "document="
            f"{document['role']} file={document['file']} "
            f"pages={document['page_count']} chars={len(document['text'])}"
        )

    if args.extract_only:
        print("extract_only=true")
        return

    processing_documents = extracted_documents
    if profile["processing_mode"] == "large_normalized_packet":
        processing_documents = [
            _build_ai_normalized_packet(
                case_dir=case_dir,
                case_id=case_id,
                customer_name=str(manifest.get("customer_name") or args.customer_name),
                account_name=str(manifest.get("account_name") or account_name),
                documents=extracted_documents,
                codex_command=args.codex_command or settings.codex_command,
                codex_model=args.codex_model or settings.codex_model,
                timeout_seconds=args.codex_timeout_seconds or settings.codex_timeout_seconds,
                chunk_chars=args.chunk_chars,
                max_chunks=args.max_chunks,
                opportunity_stage=opportunity_stage,
                processing_profile=profile,
            )
        ]
        print(
            "ai_normalized_packet="
            f"{processing_documents[0]['text_path']} chars={len(processing_documents[0]['text'])}"
        )

    source_documents = [
        DocumentRef(
            document_id=_document_id(item["file"]),
            document_type=item["role"],
            source_name=item["file"],
            content_hash=item["sha256"],
            path=str(Path("data/runtime/real_cases") / case_id / item["file"]),
            content=item["text"],
        )
        for item in processing_documents
    ]
    combined_text = _combine_documents(processing_documents)
    intake = IntakePackage(
        case_id=case_id,
        customer_name=str(manifest.get("customer_name") or args.customer_name),
        account_name=str(manifest.get("account_name") or account_name),
        intake_email_text=_field_text(processing_documents, {"opportunity_notice", "sam_notice"})
        or _package_summary(manifest, processing_documents),
        contract_text=_field_text(
            processing_documents,
            {"solicitation", "rfp", "program_solicitation", "contract_terms", "ai_normalized_packet"},
        )
        or combined_text,
        order_form_text=_field_text(
            processing_documents,
            {"pricing", "cost_volume", "order_form", "pricing_exhibit", "ai_normalized_packet"},
        )
        or combined_text,
        implementation_notes=_field_text(
            processing_documents,
            {
                "technical",
                "implementation",
                "statement_of_work",
                "performance_work_statement",
                "ai_normalized_packet",
            },
        )
        or combined_text,
        security_questionnaire_text=_field_text(
            processing_documents,
            {"security", "compliance", "cybersecurity", "data_rights", "ai_normalized_packet"},
        )
        or combined_text,
        source_documents=source_documents,
        metadata={
            "source": manifest.get("source", "local_real_case"),
            "case_dir": str(case_dir),
            "manifest": str(case_dir / "manifest.local.json"),
            "real_case": True,
            "opportunity_stage": opportunity_stage,
            "processing_mode": profile["processing_mode"],
            "processing_profile": str(case_dir / "processing_profile.local.json"),
        },
        scenario_summary=str(manifest.get("scenario_summary") or "Real government opportunity package."),
    )

    orchestrator = WorkflowOrchestrator(
        Path(args.database_path or settings.database_path),
        enable_llm_agents=True,
        codex_command=args.codex_command or settings.codex_command,
        codex_model=args.codex_model or settings.codex_model,
        codex_timeout_seconds=args.codex_timeout_seconds or settings.codex_timeout_seconds,
    )
    try:
        _delete_existing_case(orchestrator, case_id)
        orchestrator.create_case(intake)
        result = orchestrator.run_case(case_id)
        state = orchestrator.store.get_case_state(case_id)
        _write_outputs(case_dir, result.model_dump(mode="json"), state.model_dump(mode="json"))
        print(f"ran={case_id}")
        print(f"status={result.status}")
        print(f"final_route={result.routing.final_route}")
        print(f"approval_required={result.routing.approval_required}")
        print(f"findings={len(state.findings)}")
        print(f"report={case_dir / 'ai_flowops_report.local.md'}")
        print(f"state={case_dir / 'ai_flowops_state.local.json'}")
    finally:
        orchestrator.close()


def _load_or_create_manifest(
    case_dir: Path,
    case_id: str,
    customer_name: str,
    account_name: str,
) -> dict[str, Any]:
    manifest_path = case_dir / "manifest.local.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    pdfs = sorted(case_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDF files found in {case_dir}")

    manifest = {
        "case_id": case_id,
        "source": "local_government_documents",
        "customer_name": customer_name,
        "account_name": account_name,
        "scenario_summary": "Real government opportunity package imported for local AI FlowOps review.",
        "opportunity_stage": "auto",
        "processing_mode": "auto",
        "documents": [
            {
                "file": pdf.name,
                "role": _infer_role(pdf.name),
                "description": _infer_description(pdf.name),
            }
            for pdf in pdfs
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _write_manifest(case_dir: Path, manifest: dict[str, Any]) -> None:
    (case_dir / "manifest.local.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_processing_artifacts(
    case_dir: Path,
    manifest: dict[str, Any],
    documents: list[dict[str, Any]],
    profile: dict[str, Any],
) -> None:
    _write_json(case_dir / "processing_profile.local.json", profile)
    _write_json(case_dir / "document_inventory.local.json", _document_inventory(documents))
    _write_json(
        case_dir / "document_classification.local.json",
        _document_classification(manifest, documents),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _document_inventory(documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "document_count": len(documents),
        "total_pages": sum(int(item.get("page_count") or 0) for item in documents),
        "total_chars": sum(len(str(item.get("text") or "")) for item in documents),
        "documents": [
            {
                "file": item["file"],
                "role": item["role"],
                "description": item.get("description") or "",
                "page_count": item["page_count"],
                "char_count": len(str(item.get("text") or "")),
                "sha256": item["sha256"],
                "text_path": item["text_path"],
            }
            for item in documents
        ],
    }


def _document_classification(
    manifest: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_docs = {
        str(item.get("file")): item for item in manifest.get("documents", []) if item.get("file")
    }
    return {
        "classification_source": "manifest_role_with_filename_inference_fallback",
        "documents": [
            {
                "file": item["file"],
                "role": item["role"],
                "description": item.get("description")
                or str(manifest_docs.get(item["file"], {}).get("description") or ""),
                "signals": _classification_signals(item["file"], item["role"]),
            }
            for item in documents
        ],
    }


def _classification_signals(file_name: str, role: str) -> list[str]:
    lower = f"{file_name} {role}".lower()
    signals = []
    if any(token in lower for token in ("amend", "update")):
        signals.append("amendment_or_update")
    if any(token in lower for token in ("q&a", "questions", "answers", "qa_")):
        signals.append("qa_document")
    if any(token in lower for token in ("synopsis", "solicitation", "rfp", "ara")):
        signals.append("solicitation_or_program_notice")
    if any(token in lower for token in ("pricing", "cost")):
        signals.append("pricing_or_cost")
    if any(token in lower for token in ("security", "cyber", "clearance")):
        signals.append("security_or_cyber")
    return signals


def _extract_documents(case_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    extracted_dir = case_dir / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    documents = []
    for document in manifest.get("documents", []):
        file_name = str(document["file"])
        pdf_path = case_dir / file_name
        if not pdf_path.is_file():
            raise SystemExit(f"Manifest references missing PDF: {pdf_path}")
        text_path = extracted_dir / f"{pdf_path.stem}.md"
        page_texts = _extract_pdf_pages(pdf_path)
        text = _format_extracted_text(file_name, page_texts)
        text_path.write_text(text, encoding="utf-8")
        documents.append(
            {
                "file": file_name,
                "role": str(document.get("role") or _infer_role(file_name)),
                "description": str(document.get("description") or ""),
                "text_path": str(text_path),
                "text": text,
                "page_count": len(page_texts),
                "sha256": _sha256(pdf_path),
            }
        )
    return documents


def _extract_pdf_pages(pdf_path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit(
            "PDF extraction requires pypdf. Install it with: python -m pip install pypdf"
        ) from exc

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        pages.append(text or f"[No extractable text on page {index}]")
    return pages


def _format_extracted_text(file_name: str, pages: list[str]) -> str:
    sections = [f"# Extracted text: {file_name}"]
    for index, text in enumerate(pages, start=1):
        sections.append(f"## Page {index}\n{text}")
    return "\n\n".join(sections).strip() + "\n"


def _infer_role(file_name: str) -> str:
    lower = file_name.lower()
    if "amend" in lower or "update" in lower:
        return "amendment_or_update"
    if "sam" in lower and "synopsis" not in lower:
        return "opportunity_notice"
    if "synopsis" in lower or "solicitation" in lower or "rfp" in lower or "ara" in lower:
        return "program_solicitation"
    if "pricing" in lower or "cost" in lower:
        return "pricing"
    if "security" in lower or "cyber" in lower:
        return "security"
    if "technical" in lower or "pws" in lower or "sow" in lower:
        return "technical"
    return "supporting_document"


def _infer_description(file_name: str) -> str:
    role = _infer_role(file_name)
    descriptions = {
        "amendment_or_update": "Amendment, update, or program manager communication.",
        "opportunity_notice": "SAM.gov opportunity notice or listing export.",
        "program_solicitation": "Main solicitation, synopsis, or request document.",
        "pricing": "Pricing, cost, or commercial attachment.",
        "security": "Security, compliance, or cybersecurity attachment.",
        "technical": "Technical, implementation, SOW, or PWS attachment.",
        "supporting_document": "Supporting government opportunity document.",
    }
    return descriptions[role]


def _resolve_opportunity_stage(
    *,
    requested_stage: str,
    manifest: dict[str, Any],
    documents: list[dict[str, Any]],
) -> str:
    if requested_stage != "auto":
        return requested_stage

    manifest_stage = str(manifest.get("opportunity_stage") or "").strip().lower()
    if manifest_stage in {"presolicitation", "final_solicitation"}:
        return manifest_stage

    searchable = " ".join(
        [
            str(manifest.get("scenario_summary") or ""),
            str(manifest.get("account_name") or ""),
            " ".join(str(item.get("file") or "") for item in documents),
            " ".join(item["text"][:2000] for item in documents),
        ]
    ).lower()
    if any(
        token in searchable
        for token in (
            "presolicitation",
            "pre-solicitation",
            "pre solicitation",
            "synopsis",
            "advanced research announcement",
            "ara",
        )
    ):
        return "presolicitation"
    return "final_solicitation"


def _document_id(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _field_text(documents: list[dict[str, Any]], roles: set[str]) -> str:
    selected = [item["text"] for item in documents if item["role"] in roles]
    return "\n\n".join(selected).strip()


def _combine_documents(documents: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"# {item['file']} ({item['role']})\n\n{item['text']}" for item in documents
    ).strip()


def _package_summary(manifest: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    lines = [
        f"Case id: {manifest.get('case_id')}",
        f"Source: {manifest.get('source')}",
        f"Account: {manifest.get('account_name')}",
        "Downloaded document package:",
    ]
    lines.extend(f"- {item['file']} ({item['role']})" for item in documents)
    return "\n".join(lines)


def _build_ai_normalized_packet(
    *,
    case_dir: Path,
    case_id: str,
    customer_name: str,
    account_name: str,
    documents: list[dict[str, Any]],
    codex_command: str,
    codex_model: str,
    timeout_seconds: int,
    chunk_chars: int,
    max_chunks: int,
    opportunity_stage: str,
    processing_profile: dict[str, Any],
) -> dict[str, Any]:
    from agents.openai_review import CodexReviewAgent
    from schemas.case import DocumentRef, IntakePackage

    agent = CodexReviewAgent(
        command=codex_command,
        model=codex_model,
        timeout_seconds=timeout_seconds,
    )
    sections = [
        "# AI-normalized real-case packet",
        "",
        f"Case id: {case_id}",
        f"Customer: {customer_name}",
        f"Opportunity: {account_name}",
        "",
        (
            "This packet was generated by running Codex over chunks of the original "
            "government PDFs. Source filenames, page ranges, exact quotes, and "
            "normalized facts are preserved so downstream reviewers can verify the "
            "AI analysis against the original document package."
        ),
        "",
        "## Processing profile",
        f"- Processing mode: {processing_profile['processing_mode']}",
        f"- Complexity score: {processing_profile['complexity_score']}",
        f"- Trigger reasons: {', '.join(processing_profile['trigger_reasons']) or 'none'}",
        "",
        "## Source documents processed",
    ]
    for document in documents:
        sections.append(
            f"- {document['file']} ({document['role']}), pages={document['page_count']}, "
            f"sha256={document['sha256']}"
        )

    finding_count = 0
    evidence_count = 0
    chunk_count = 0
    chunk_reviews: list[dict[str, Any]] = []
    text_path = case_dir / "extracted" / "ai_normalized_packet.local.md"
    chunk_reviews_path = case_dir / "chunk_reviews.local.json"
    for chunk in _document_chunks(documents, chunk_chars):
        chunk_count += 1
        chunk_id = f"chunk-{chunk_count:03d}"
        if max_chunks and chunk_count > max_chunks:
            sections.extend(["", f"## Chunk limit reached for debug run: {max_chunks}"])
            break
        print(
            "ai_chunk="
            f"{chunk_count} source={chunk['file']} pages={chunk['pages']} chars={len(chunk['text'])}"
            ,
            flush=True,
        )
        chunk_case_id = f"{case_id}-chunk-{chunk_count:03d}"
        chunk_ref = DocumentRef(
            document_id=f"{_document_id(chunk['file'])}_chunk_{chunk_count:03d}",
            document_type=chunk["role"],
            source_name=f"{chunk['file']} pages {chunk['pages']}",
            content_hash=chunk["sha256"],
            path=str(Path("data/runtime/real_cases") / case_id / chunk["file"]),
            content=chunk["text"],
        )
        intake = IntakePackage(
            case_id=chunk_case_id,
            customer_name=customer_name,
            account_name=account_name,
            intake_email_text=chunk["text"],
            contract_text=chunk["text"],
            order_form_text=chunk["text"],
            implementation_notes=chunk["text"],
            security_questionnaire_text=chunk["text"],
            source_documents=[chunk_ref],
            metadata={
                "source": "real_case_chunk",
                "source_file": chunk["file"],
                "pages": chunk["pages"],
                "opportunity_stage": opportunity_stage,
                "processing_mode": "large_normalized_packet",
            },
        )
        evidence, findings, _trace = agent.run(intake)
        evidence_count += len(evidence)
        finding_count += len(findings)
        chunk_reviews.append(
            {
                "chunk_id": chunk_id,
                "source_file": chunk["file"],
                "role": chunk["role"],
                "pages": chunk["pages"],
                "chars": len(chunk["text"]),
                "evidence_count": len(evidence),
                "finding_count": len(findings),
                "findings": [
                    {
                        "rule_id": finding.rule_id,
                        "route": finding.route,
                        "severity": finding.severity,
                        "summary": finding.summary,
                        "confidence": finding.confidence,
                        "evidence": [
                            {
                                "source_file": chunk["file"],
                                "pages": chunk["pages"],
                                "locator": item.locator,
                                "quote": item.quote,
                                "normalized_fact": item.normalized_fact,
                                "confidence": item.confidence,
                            }
                            for item in finding.evidence
                        ],
                    }
                    for finding in findings
                ],
            }
        )
        sections.extend(
            [
                "",
                f"## AI chunk review: {chunk_id} - {chunk['file']} pages {chunk['pages']}",
                f"- Findings: {len(findings)}",
                f"- Evidence items: {len(evidence)}",
            ]
        )
        if not findings:
            sections.append("- No material commercial intake risk found in this chunk.")
        for finding in findings:
            sections.extend(
                [
                    "",
                    f"### {finding.rule_id} ({finding.route}, {finding.severity})",
                    f"- Summary: {finding.summary}",
                    f"- Confidence: {finding.confidence}",
                ]
            )
            for item in finding.evidence:
                sections.extend(
                    [
                        f"- Source: {chunk_id} / {chunk['file']} pages {chunk['pages']} / {item.locator}",
                        f"- Quote: {item.quote}",
                        f"- Normalized fact: {item.normalized_fact}",
                    ]
                )
        text_path.write_text("\n".join(sections).strip() + "\n", encoding="utf-8")

    sections.extend(
        [
            "",
            "## Digest totals",
            f"- Chunks processed by Codex: {chunk_count}",
            f"- AI evidence items: {evidence_count}",
            f"- AI findings: {finding_count}",
        ]
    )

    text = "\n".join(sections).strip() + "\n"
    text_path.write_text(text, encoding="utf-8")
    chunk_reviews_path.write_text(json.dumps(chunk_reviews, indent=2), encoding="utf-8")
    return {
        "file": text_path.name,
        "role": "ai_normalized_packet",
        "description": "AI-normalized packet generated from original government PDFs.",
        "text_path": str(text_path),
        "text": text,
        "page_count": chunk_count,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chunk_reviews_path": str(chunk_reviews_path),
    }


def _document_chunks(documents: list[dict[str, Any]], chunk_chars: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents:
        pages = _split_extracted_pages(document["text"])
        current_pages: list[int] = []
        current_text: list[str] = []
        current_len = 0
        for page_number, page_text in pages:
            page_len = len(page_text)
            if current_text and current_len + page_len > chunk_chars:
                chunks.append(_make_chunk(document, current_pages, current_text))
                current_pages = []
                current_text = []
                current_len = 0
            current_pages.append(page_number)
            current_text.append(f"## Page {page_number}\n{page_text}")
            current_len += page_len
        if current_text:
            chunks.append(_make_chunk(document, current_pages, current_text))
    return chunks


def _split_extracted_pages(text: str) -> list[tuple[int, str]]:
    matches = list(re.finditer(r"^## Page (\d+)\s*$", text, flags=re.MULTILINE))
    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages.append((int(match.group(1)), text[start:end].strip()))
    return pages or [(1, text)]


def _make_chunk(
    document: dict[str, Any],
    pages: list[int],
    page_sections: list[str],
) -> dict[str, Any]:
    page_label = _page_label(pages)
    text = (
        f"# Source file: {document['file']}\n"
        f"Role: {document['role']}\n"
        f"Pages: {page_label}\n\n"
        + "\n\n".join(page_sections)
    )
    return {
        "file": document["file"],
        "role": document["role"],
        "pages": page_label,
        "text": text,
        "sha256": document["sha256"],
    }


def _page_label(pages: list[int]) -> str:
    if not pages:
        return "unknown"
    if len(pages) == 1:
        return str(pages[0])
    return f"{pages[0]}-{pages[-1]}"


def _delete_existing_case(orchestrator: Any, case_id: str) -> None:
    orchestrator.store.conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
    orchestrator.store.conn.commit()


def _write_outputs(case_dir: Path, run_result: dict[str, Any], state: dict[str, Any]) -> None:
    state_path = case_dir / "ai_flowops_state.local.json"
    result_path = case_dir / "ai_flowops_result.local.json"
    report_path = case_dir / "ai_flowops_report.local.md"
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    result_path.write_text(json.dumps(run_result, indent=2), encoding="utf-8")
    report_path.write_text(_render_report(run_result, state), encoding="utf-8")


def _render_report(run_result: dict[str, Any], state: dict[str, Any]) -> str:
    routing = state.get("routing_decision") or {}
    findings = state.get("findings") or []
    lines = [
        f"# AI FlowOps real-case report: {state.get('case_id')}",
        "",
        "## Routing",
        f"- Status: {run_result.get('status')}",
        f"- Final route: {routing.get('recommended_route') or run_result.get('routing', {}).get('final_route')}",
        f"- Approval required: {routing.get('approval_required')}",
        f"- Confidence: {routing.get('confidence')}",
        f"- Reasons: {', '.join(routing.get('reasons') or []) or 'None'}",
        "",
        "## Findings",
    ]
    if not findings:
        lines.append("- No findings returned.")
    for finding in findings:
        lines.extend(
            [
                f"### {finding.get('rule_id')} ({finding.get('route')}, {finding.get('severity')})",
                f"- Summary: {finding.get('summary')}",
                f"- Confidence: {finding.get('confidence')}",
            ]
        )
        for evidence in finding.get("evidence") or []:
            lines.extend(
                [
                    f"  - Source: {evidence.get('source_document_type')} {evidence.get('locator')}",
                    f"  - Quote: {evidence.get('quote')}",
                    f"  - Fact: {evidence.get('normalized_fact')}",
                ]
            )
    return "\n".join(lines).strip() + "\n"


if __name__ == "__main__":
    main()
