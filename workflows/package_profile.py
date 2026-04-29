from __future__ import annotations

from typing import Any, Literal

ProcessingMode = Literal["simple_direct_ai", "large_normalized_packet"]
ProcessingModeRequest = Literal["auto", "simple", "large"]

DEFAULT_TOTAL_CHAR_THRESHOLD = 60_000
DEFAULT_LARGEST_DOC_CHAR_THRESHOLD = 40_000
DEFAULT_DOCUMENT_COUNT_THRESHOLD = 8
DEFAULT_PAGE_THRESHOLD = 75


def build_package_profile(
    *,
    manifest: dict[str, Any],
    documents: list[dict[str, Any]],
    requested_mode: ProcessingModeRequest = "auto",
    total_char_threshold: int = DEFAULT_TOTAL_CHAR_THRESHOLD,
) -> dict[str, Any]:
    metrics = _metrics(documents)
    trigger_reasons = _trigger_reasons(
        metrics=metrics,
        total_char_threshold=total_char_threshold,
        manifest=manifest,
        requested_mode=requested_mode,
    )
    processing_mode: ProcessingMode = (
        "large_normalized_packet" if trigger_reasons else "simple_direct_ai"
    )

    return {
        "processing_mode": processing_mode,
        "requested_mode": requested_mode,
        "complexity_score": _complexity_score(metrics, trigger_reasons),
        "trigger_reasons": trigger_reasons,
        "metrics": metrics,
        "notes": [
            (
                "Use simple direct AI extraction when the package fits comfortably "
                "in one review pass."
            ),
            (
                "Use large normalized-packet processing when the package is dense, "
                "multi-document, amendment-heavy, or likely to exceed a safe prompt budget."
            ),
        ],
    }


def _metrics(documents: list[dict[str, Any]]) -> dict[str, Any]:
    total_chars = sum(len(str(item.get("text") or "")) for item in documents)
    total_pages = sum(int(item.get("page_count") or 0) for item in documents)
    largest = max(documents, key=lambda item: len(str(item.get("text") or "")), default={})
    role_counts: dict[str, int] = {}
    for document in documents:
        role = str(document.get("role") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1

    return {
        "document_count": len(documents),
        "total_pages": total_pages,
        "total_chars": total_chars,
        "estimated_tokens": max(1, total_chars // 4) if total_chars else 0,
        "largest_document_file": str(largest.get("file") or ""),
        "largest_document_chars": len(str(largest.get("text") or "")),
        "amendment_or_update_detected": any(_is_amendment_or_update(item) for item in documents),
        "qa_detected": any(_is_qa_document(item) for item in documents),
        "role_counts": role_counts,
        "post_ai_quality_gate": "not_evaluated_before_ai_review",
    }


def _trigger_reasons(
    *,
    metrics: dict[str, Any],
    total_char_threshold: int,
    manifest: dict[str, Any],
    requested_mode: ProcessingModeRequest,
) -> list[str]:
    if requested_mode == "simple":
        return []
    if requested_mode == "large":
        return ["forced_by_cli_large"]

    manifest_mode = str(manifest.get("processing_mode") or "").strip().lower()
    if manifest_mode in {"simple", "simple_direct_ai"}:
        return []
    if manifest_mode in {"large", "large_normalized_packet"}:
        return ["forced_by_manifest_large"]

    reasons = []
    if int(metrics["document_count"]) > DEFAULT_DOCUMENT_COUNT_THRESHOLD:
        reasons.append("document_count_gt_8")
    if int(metrics["total_pages"]) > DEFAULT_PAGE_THRESHOLD:
        reasons.append("total_pages_gt_75")
    if total_char_threshold and int(metrics["total_chars"]) > total_char_threshold:
        reasons.append("total_chars_gt_threshold")
    if int(metrics["largest_document_chars"]) > DEFAULT_LARGEST_DOC_CHAR_THRESHOLD:
        reasons.append("largest_document_chars_gt_40000")
    if bool(metrics["amendment_or_update_detected"]):
        reasons.append("amendment_or_update_detected")
    if bool(metrics["qa_detected"]):
        reasons.append("qa_document_detected")
    return reasons


def _complexity_score(metrics: dict[str, Any], trigger_reasons: list[str]) -> int:
    score = len(trigger_reasons) * 20
    score += min(int(metrics["document_count"]) * 3, 24)
    score += min(int(metrics["total_pages"]) // 5, 24)
    score += min(int(metrics["estimated_tokens"]) // 5_000, 20)
    return min(score, 100)


def _is_amendment_or_update(document: dict[str, Any]) -> bool:
    searchable = f"{document.get('file', '')} {document.get('role', '')}".lower()
    return any(token in searchable for token in ("amend", "update", "q&a", "qa"))


def _is_qa_document(document: dict[str, Any]) -> bool:
    searchable = f"{document.get('file', '')} {document.get('role', '')}".lower()
    return any(token in searchable for token in ("q&a", "questions", "answers", "qa_"))
