from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

CASE_PATH = Path("data/guided_demo/flagship_case.json")
DOCUMENTS_DIR = Path("data/guided_demo/documents")
RUNTIME_DIR = Path("data/runtime")
DEFAULT_OUTPUT = RUNTIME_DIR / "guided-demo-ai-candidate.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a local Codex-backed guided demo AI candidate."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--model", default=os.getenv("CODEX_MODEL", "gpt-5.4"))
    parser.add_argument("--codex-command", default=os.getenv("CODEX_COMMAND", "codex"))
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("CODEX_TIMEOUT_SECONDS", "300")),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt and validate no Codex output. Does not consume tokens.",
    )
    args = parser.parse_args()

    prompt = build_codex_prompt()
    if args.dry_run:
        print(prompt)
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_message_path = output_path.with_suffix(".last-message.txt")

    command = [
        resolve_codex_command(args.codex_command),
        "exec",
        "--cd",
        str(Path.cwd()),
        "--sandbox",
        "read-only",
        "-m",
        args.model,
        "--output-last-message",
        str(raw_message_path),
        "-",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        input=prompt,
        timeout=args.timeout,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "codex exec failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

    raw_message = raw_message_path.read_text(encoding="utf-8")
    candidate = parse_json_payload(raw_message)
    validate_candidate(candidate, load_document_texts())
    output_path.write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote={output_path}")
    print(
        "screening="
        f"{candidate['screening']['recommendation']} "
        f"confidence={candidate['screening']['confidence']}"
    )


def build_codex_prompt() -> str:
    demo = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    document_paths = "\n".join(
        f"- {path.stem}: {path.as_posix()}" for path in sorted(DOCUMENTS_DIR.glob("*.md"))
    )
    return f"""
You are generating the local AI-prep candidate for a read-only portfolio demo.
Do not edit files. Read the source documents listed below. Return only valid JSON.

Goal:
Analyze the full synthetic government RFP package in two AI layers.

Layer 1 - AI Screening:
- Treat the package as one candidate from a broader overnight government-opportunity feed.
- Decide whether this RFP should be promoted for contract-fit bid/no-bid analysis.
- Explain the screening recommendation with grounded source reasons.

Layer 2 - AI Case Analysis:
- Extract the main facts.
- Identify material risks.
- Recommend whether to bid.
- Route department-specific packets for Legal, Security, Finance, and Implementation.
- Produce an AI synthesis packet for BD/Ops.
- Include confidence levels and source quotes.

Current public demo case for context:
{json.dumps(demo["case"], indent=2)}

Source document files to read:
{document_paths}

Required JSON shape:
{{
  "screening": {{
    "recommendation": "Promote for bid/no-bid analysis",
    "confidence": 0.0,
    "opportunities_scanned_assumption": 43,
    "source_reasons": [
      {{
        "document_id": "rfp",
        "quote": "exact quote from source document",
        "reason": "why this supports screening"
      }}
    ]
  }},
  "case_analysis": {{
    "recommendation": "conditional bid, no bid, or needs more information",
    "confidence": 0.0,
    "summary": "plain English summary",
    "risk_flags": [
      {{
        "label": "risk label",
        "department": "Legal|Security|Finance|Implementation",
        "confidence": 0.0,
        "document_id": "rfp",
        "quote": "exact quote from source document"
      }}
    ],
    "department_packets": [
      {{
        "department": "Legal|Security|Finance|Implementation",
        "precis": "memo-style paragraph for the human reviewer",
        "recommendation": "concrete specialist action",
        "supporting_facts": [
          {{
            "fact": "fact sent to reviewer",
            "document_id": "rfp",
            "quote": "exact quote from source document"
          }}
        ],
        "questions": ["question for reviewer"]
      }}
    ],
    "ai_synthesis": {{
      "headline": "BD/Ops-facing recommendation",
      "summary": "full synthesis for BD/Ops",
      "conditions": ["condition"]
    }}
  }}
}}

Rules:
- Use exact source quotes. Do not invent quotes.
- It is acceptable if your conclusions differ from the existing fixture, as long as
  they are grounded.
- AI recommends; humans and BD/Ops own decisions.
- Public demo output will be precomputed and read-only.
""".strip()


def load_document_texts() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(DOCUMENTS_DIR.glob("*.md"))
    }


def resolve_codex_command(command: str) -> str:
    if os.name == "nt" and not Path(command).suffix:
        cmd_path = shutil.which(f"{command}.cmd")
        if cmd_path:
            return cmd_path
    resolved = shutil.which(command)
    return resolved or command


def parse_json_payload(raw_message: str) -> dict[str, Any]:
    cleaned = raw_message.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def validate_candidate(candidate: dict[str, Any], documents: dict[str, str]) -> None:
    screening = candidate.get("screening")
    if not isinstance(screening, dict):
        raise ValueError("candidate missing screening object")
    if not screening.get("recommendation"):
        raise ValueError("screening missing recommendation")
    if screening.get("confidence") is None:
        raise ValueError("screening missing confidence")
    source_reasons = screening.get("source_reasons")
    if not isinstance(source_reasons, list) or not source_reasons:
        raise ValueError("screening missing grounded source_reasons")
    for reason in source_reasons:
        _validate_quote(reason, documents, "screening.source_reasons")

    analysis = candidate.get("case_analysis")
    if not isinstance(analysis, dict):
        raise ValueError("candidate missing case_analysis object")
    if not analysis.get("department_packets"):
        raise ValueError("case_analysis missing department_packets")
    if not analysis.get("ai_synthesis"):
        raise ValueError("case_analysis missing ai_synthesis")

    for risk in analysis.get("risk_flags", []):
        _validate_quote(risk, documents, "case_analysis.risk_flags")
    for packet in analysis.get("department_packets", []):
        if not packet.get("precis") or not packet.get("recommendation"):
            raise ValueError("department packet missing precis or recommendation")
        for fact in packet.get("supporting_facts", []):
            _validate_quote(fact, documents, "department_packets.supporting_facts")


def _validate_quote(item: dict[str, Any], documents: dict[str, str], location: str) -> None:
    document_id = item.get("document_id")
    quote = item.get("quote")
    if document_id not in documents:
        raise ValueError(f"{location} references unknown document_id={document_id!r}")
    if not quote:
        raise ValueError(f"{location} missing quote")
    if _normalize(quote) not in _normalize(documents[document_id]):
        raise ValueError(f"{location} quote not found in {document_id}: {quote!r}")


def _normalize(value: str) -> str:
    return " ".join(value.lower().split()).replace("’", "'").replace("“", '"').replace("”", '"')


if __name__ == "__main__":
    main()
