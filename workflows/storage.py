from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schemas.case import (
    Approval,
    ApprovalStatus,
    CaseStatus,
    EvalResult,
    Finding,
    GeneratedBrief,
    GeneratedTask,
    IntakePackage,
    KPIRecord,
    NormalizedCase,
    RoutingDecision,
    SeedCase,
    TraceRecord,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_json(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _from_json(payload: str | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return json.loads(payload)


@dataclass(frozen=True)
class CaseListItem:
    case_id: str
    customer_name: str
    account_name: str | None
    state: CaseStatus
    route: str | None
    final_route: str | None
    expected_route: str | None
    expected_approval_required: bool


class WorkflowStorage:
    def __init__(self, db_path: str = "data/runtime/app.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    account_name TEXT,
                    state TEXT NOT NULL,
                    expected_route TEXT,
                    expected_approval_required INTEGER,
                    expected_key_risk_labels TEXT,
                    expected_task_owner_category TEXT,
                    scenario_summary TEXT,
                    submitted_at TEXT,
                    raw_payload TEXT NOT NULL,
                    normalized_payload TEXT,
                    final_route TEXT,
                    routing_decision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    finding_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    route TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS routing_decisions (
                    case_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    reviewer TEXT,
                    comments TEXT,
                    original_route TEXT NOT NULL,
                    final_route TEXT,
                    requested_info TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS generated_outputs (
                    output_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    output_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    owner_function TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    due_category TEXT NOT NULL,
                    source_finding_ids TEXT NOT NULL,
                    evidence_references TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS trace_records (
                    trace_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    model_provider_label TEXT NOT NULL,
                    inputs_summary TEXT NOT NULL,
                    outputs_summary TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );

                CREATE TABLE IF NOT EXISTS eval_results (
                    case_id TEXT PRIMARY KEY,
                    expected_route TEXT,
                    actual_route TEXT NOT NULL,
                    route_pass INTEGER NOT NULL,
                    grounding_pass INTEGER NOT NULL,
                    approval_pass INTEGER NOT NULL,
                    brief_completeness_pass INTEGER NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kpi_records (
                    case_id TEXT PRIMARY KEY,
                    final_route TEXT NOT NULL,
                    straight_through INTEGER NOT NULL,
                    approval_required INTEGER NOT NULL,
                    reviewer_override INTEGER NOT NULL DEFAULT 0,
                    processing_time_ms INTEGER,
                    generated_task_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id)
                );
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path.as_posix())
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def clear(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM eval_results")
            cur.execute("DELETE FROM trace_records")
            cur.execute("DELETE FROM tasks")
            cur.execute("DELETE FROM generated_outputs")
            cur.execute("DELETE FROM approvals")
            cur.execute("DELETE FROM routing_decisions")
            cur.execute("DELETE FROM findings")
            cur.execute("DELETE FROM documents")
            cur.execute("DELETE FROM kpi_records")
            cur.execute("DELETE FROM cases")

    def upsert_case(self, case: IntakePackage | SeedCase, state: CaseStatus = "draft") -> None:
        payload = _to_json(case)
        expected_route = getattr(case, "expected_route", None)
        expected_approval = getattr(case, "expected_approval_required", None)
        expected_risks = getattr(case, "expected_key_risk_labels", None)
        expected_owner = getattr(case, "expected_task_owner_category", None)
        scenario_summary = getattr(case, "scenario_summary", "")
        submitted_at = case.submitted_at.isoformat()

        expected_approval_int = int(bool(expected_approval)) if expected_approval is not None else 0
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO cases (
                    case_id, customer_name, account_name, state,
                    expected_route, expected_approval_required, expected_key_risk_labels,
                    expected_task_owner_category, scenario_summary, submitted_at,
                    raw_payload, normalized_payload, final_route, routing_decision_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    customer_name=excluded.customer_name,
                    account_name=excluded.account_name,
                    state=excluded.state,
                    expected_route=excluded.expected_route,
                    expected_approval_required=excluded.expected_approval_required,
                    expected_key_risk_labels=excluded.expected_key_risk_labels,
                    expected_task_owner_category=excluded.expected_task_owner_category,
                    scenario_summary=excluded.scenario_summary,
                    raw_payload=excluded.raw_payload,
                    updated_at=excluded.updated_at
                """,
                (
                    case.case_id,
                    case.customer_name,
                    case.account_name,
                    state,
                    expected_route,
                    expected_approval_int,
                    json.dumps(expected_risks or []),
                    expected_owner,
                    scenario_summary,
                    submitted_at,
                    payload,
                    None,
                    None,
                    None,
                    _now_iso(),
                    _now_iso(),
                ),
            )

    def save_normalized_case(self, case: NormalizedCase) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cases SET normalized_payload=?, updated_at=?, state=? WHERE case_id=?",
                (_to_json(case), _now_iso(), "normalized", case.case_id),
            )
            conn.execute("DELETE FROM documents WHERE case_id=?", (case.case_id,))
            for doc in case.document_refs:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents(
                        document_id, case_id, payload, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (doc.document_id, case.case_id, doc.model_dump_json(), _now_iso()),
                )

    def get_case(self, case_id: str) -> IntakePackage | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT raw_payload FROM cases WHERE case_id = ?", (case_id,)
            ).fetchone()
        if not row:
            return None
        payload = _from_json(row["raw_payload"])
        if not payload:
            return None
        return IntakePackage.model_validate(payload)

    def list_cases(
        self, route: str | None = None, state: str | None = None, search: str | None = None
    ) -> list[CaseListItem]:
        query = (
            "SELECT case_id, customer_name, account_name, state, final_route, "
            "expected_route, expected_approval_required FROM cases"
        )
        clauses: list[str] = []
        params: list[object] = []
        if route:
            clauses.append("final_route = ?")
            params.append(route)
        if state:
            clauses.append("state = ?")
            params.append(state)
        if search:
            clauses.append(
                "CASE WHEN customer_name LIKE ? OR account_name LIKE ? THEN 1 ELSE 0 END = 1"
            )
            params.extend([f"%{search}%", f"%{search}%"])
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            CaseListItem(
                case_id=row["case_id"],
                customer_name=row["customer_name"],
                account_name=row["account_name"],
                state=row["state"],  # type: ignore[assignment]
                route=row["final_route"] if row["final_route"] else None,
                final_route=row["final_route"] if row["final_route"] else None,
                expected_route=row["expected_route"],
                expected_approval_required=bool(row["expected_approval_required"]),
            )
            for row in rows
        ]

    def save_findings(self, case_id: str, findings: Iterable[Finding]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
            for finding in findings:
                payload = _to_json(finding)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO findings
                    (
                        finding_id, case_id, payload, rule_id, finding_type,
                        severity, route, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        finding.finding_id,
                        case_id,
                        payload,
                        finding.rule_id,
                        finding.finding_type,
                        finding.severity,
                        finding.route,
                        _now_iso(),
                    ),
                )

    def save_routing_decision(self, case_id: str, decision: RoutingDecision) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cases SET final_route=?, state='routed' WHERE case_id=?",
                (decision.recommended_route, case_id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO routing_decisions(case_id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (case_id, _to_json(decision), _now_iso()),
            )

    def get_routing_decision(self, case_id: str) -> RoutingDecision | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM routing_decisions WHERE case_id=?", (case_id,)
            ).fetchone()
        if not row:
            return None
        payload = _from_json(row["payload"])
        if not payload:
            return None
        return RoutingDecision.model_validate(payload)

    def find_case_findings(self, case_id: str) -> list[Finding]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM findings WHERE case_id=? ORDER BY created_at", (case_id,)
            ).fetchall()
        findings = []
        for row in rows:
            payload = _from_json(row["payload"])
            if payload:
                findings.append(Finding.model_validate(payload))
        return findings

    def create_approval(self, approval: Approval) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cases SET state='awaiting_approval' WHERE case_id=?", (approval.case_id,)
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO approvals
                (
                    approval_id, case_id, status, reviewer, comments,
                    original_route, final_route, requested_info, created_at, resolved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.approval_id,
                    approval.case_id,
                    approval.status,
                    approval.reviewer,
                    approval.comments,
                    approval.original_route,
                    approval.final_route,
                    approval.requested_info,
                    approval.created_at.isoformat(),
                    approval.resolved_at.isoformat() if approval.resolved_at else None,
                ),
            )

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
        if not row:
            return None
        return Approval.model_validate(
            {
                "approval_id": row["approval_id"],
                "case_id": row["case_id"],
                "status": row["status"],
                "reviewer": row["reviewer"],
                "comments": row["comments"],
                "original_route": row["original_route"],
                "final_route": row["final_route"],
                "requested_info": row["requested_info"],
                "created_at": row["created_at"],
                "resolved_at": row["resolved_at"],
            }
        )

    def get_approval_by_case(self, case_id: str) -> Approval | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE case_id=? ORDER BY created_at DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_approval(row)

    def _row_to_approval(self, row: sqlite3.Row) -> Approval:
        return Approval.model_validate(
            {
                "approval_id": row["approval_id"],
                "case_id": row["case_id"],
                "status": row["status"],
                "reviewer": row["reviewer"],
                "comments": row["comments"],
                "original_route": row["original_route"],
                "final_route": row["final_route"],
                "requested_info": row["requested_info"],
                "created_at": row["created_at"],
                "resolved_at": row["resolved_at"],
            }
        )

    def list_approvals(self, status: ApprovalStatus | None = None) -> list[Approval]:
        query = "SELECT * FROM approvals"
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def update_approval_status(
        self, approval_id: str, status: ApprovalStatus, **patch: Any
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT case_id FROM approvals WHERE approval_id=?", (approval_id,)
            ).fetchone()
            if not row:
                return
            case_id = row["case_id"]
            assignments = ["status=?", "resolved_at=?"]
            values: list[Any] = [status, _now_iso()]
            if "comments" in patch:
                assignments.append("comments=?")
                values.append(patch["comments"])
            if "final_route" in patch:
                assignments.append("final_route=?")
                values.append(patch["final_route"])
            if "requested_info" in patch:
                assignments.append("requested_info=?")
                values.append(patch["requested_info"])
            if "reviewer" in patch:
                assignments.append("reviewer=?")
                values.append(patch["reviewer"])
            values.append(approval_id)
            conn.execute(
                f"UPDATE approvals SET {', '.join(assignments)} WHERE approval_id=?", values
            )

            case_state = (
                "completed"
                if status in {"approved", "override_route"}
                else ("draft" if status in {"request_info", "rejected"} else "awaiting_approval")
            )
            if status == "rejected":
                case_state = "rejected"
            conn.execute("UPDATE cases SET state=? WHERE case_id=?", (case_state, case_id))

    def save_brief(self, brief: GeneratedBrief) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO generated_outputs(
                    output_id, case_id, output_type, payload, created_at
                )
                VALUES (?, ?, 'brief', ?, ?)
                """,
                (brief.case_id, brief.case_id, brief.model_dump_json(), _now_iso()),
            )
            conn.execute(
                "UPDATE cases SET final_route=? WHERE case_id=?", (brief.final_route, brief.case_id)
            )

    def save_tasks(self, tasks: list[GeneratedTask]) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM tasks WHERE case_id=?",
                tuple(t.case_id for t in tasks[:1] or [None]) or ("",),
            )
            for task in tasks:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks(
                        task_id, case_id, title, owner_function, priority, due_category,
                        source_finding_ids,
                        evidence_references, status, created_at, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.case_id,
                        task.title,
                        task.owner_function,
                        task.priority,
                        task.due_category,
                        json.dumps(task.source_finding_ids),
                        json.dumps(task.evidence_references),
                        task.status,
                        _now_iso(),
                        task.model_dump_json(),
                    ),
                )

    def list_tasks(self, case_id: str | None = None) -> list[GeneratedTask]:
        query = "SELECT payload FROM tasks"
        params: list[object] = []
        if case_id:
            query += " WHERE case_id = ?"
            params.append(case_id)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        tasks: list[GeneratedTask] = []
        for row in rows:
            payload = _from_json(row["payload"])
            if payload:
                tasks.append(GeneratedTask.model_validate(payload))
        return tasks

    def get_brief(self, case_id: str) -> GeneratedBrief | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM generated_outputs WHERE case_id=? AND output_type='brief'",
                (case_id,),
            ).fetchone()
        if not row:
            return None
        payload = _from_json(row["payload"])
        return GeneratedBrief.model_validate(payload) if payload else None

    def save_trace(self, trace: TraceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_records(
                    trace_id, case_id, step_name, agent_name, model_provider_label,
                    inputs_summary, outputs_summary, latency_ms, token_count, cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{trace.case_id}:{trace.step_name}:{trace.created_at.timestamp()}",
                    trace.case_id,
                    trace.step_name,
                    trace.agent_name,
                    trace.model_provider_label,
                    trace.inputs_summary,
                    trace.outputs_summary,
                    trace.latency_ms,
                    trace.token_count,
                    trace.cost_usd,
                    trace.created_at.isoformat(),
                ),
            )

    def list_traces(self, case_id: str) -> list[TraceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trace_records WHERE case_id = ? ORDER BY created_at, trace_id",
                (case_id,),
            ).fetchall()
        out: list[TraceRecord] = []
        for row in rows:
            out.append(
                TraceRecord(
                    case_id=row["case_id"],
                    step_name=row["step_name"],
                    agent_name=row["agent_name"],
                    model_provider_label=row["model_provider_label"],
                    inputs_summary=row["inputs_summary"],
                    outputs_summary=row["outputs_summary"],
                    latency_ms=row["latency_ms"],
                    token_count=row["token_count"],
                    cost_usd=row["cost_usd"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return out

    def save_eval_result(self, result: EvalResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_results(
                    case_id, expected_route, actual_route, route_pass, grounding_pass,
                    approval_pass, brief_completeness_pass, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.case_id,
                    result.expected_route,
                    result.actual_route,
                    int(result.route_pass),
                    int(result.grounding_pass),
                    int(result.approval_pass),
                    int(result.brief_completeness_pass),
                    result.notes,
                    _now_iso(),
                ),
            )

    def list_eval_results(self) -> list[EvalResult]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM eval_results").fetchall()
        out: list[EvalResult] = []
        for row in rows:
            out.append(
                EvalResult(
                    case_id=row["case_id"],
                    expected_route=row["expected_route"],
                    actual_route=row["actual_route"],
                    route_pass=bool(row["route_pass"]),
                    grounding_pass=bool(row["grounding_pass"]),
                    approval_pass=bool(row["approval_pass"]),
                    brief_completeness_pass=bool(row["brief_completeness_pass"]),
                    notes=row["notes"],
                )
            )
        return out

    def save_kpi(self, kpi: KPIRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO kpi_records(
                    case_id, final_route, straight_through, approval_required, reviewer_override,
                    processing_time_ms, generated_task_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kpi.case_id,
                    kpi.final_route,
                    int(kpi.straight_through),
                    int(kpi.approval_required),
                    int(kpi.reviewer_override),
                    kpi.processing_time_ms,
                    kpi.generated_task_count,
                    _now_iso(),
                ),
            )

    def compute_kpi_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM cases").fetchone()["c"]
            awaiting = conn.execute(
                "SELECT COUNT(*) AS c FROM cases WHERE state='awaiting_approval'"
            ).fetchone()["c"]
            approved = conn.execute(
                "SELECT COUNT(*) AS c FROM cases WHERE state='approved'"
            ).fetchone()["c"]
            completed = conn.execute(
                "SELECT COUNT(*) AS c FROM cases WHERE state='completed'"
            ).fetchone()["c"]
            rejected = conn.execute(
                "SELECT COUNT(*) AS c FROM cases WHERE state='rejected'"
            ).fetchone()["c"]
            overrides = conn.execute(
                "SELECT COUNT(*) AS c FROM approvals WHERE status='override_route'"
            ).fetchone()["c"]
            route_rows = conn.execute(
                "SELECT final_route, COUNT(*) AS c FROM kpi_records GROUP BY final_route"
            ).fetchall()

        route_distribution = {
            row["final_route"] if row["final_route"] else "unknown": row["c"] for row in route_rows
        }
        straight_through = (
            conn.execute(
                "SELECT COUNT(*) AS c FROM kpi_records WHERE straight_through=1"
            ).fetchone()["c"]
            if total
            else 0
        )
        eval_summary = self.list_eval_results()
        pass_count = sum(
            1
            for e in eval_summary
            if e.route_pass and e.approval_pass and e.grounding_pass and e.brief_completeness_pass
        )

        return {
            "total_cases": int(total),
            "pending_approvals": int(awaiting),
            "completed_cases": int(completed),
            "approved_cases": int(approved),
            "rejected_cases": int(rejected),
            "straight_through": int(straight_through),
            "straight_through_rate": (int(straight_through) / max(1, int(total))) * 100
            if total
            else 0.0,
            "escalation_rate": ((int(approved) + int(rejected)) / max(1, int(total))) * 100
            if total
            else 0.0,
            "override_count": int(overrides),
            "override_rate": (int(overrides) / max(1, int(total))) * 100 if total else 0.0,
            "route_distribution": route_distribution,
            "request_info_count": conn.execute(
                "SELECT COUNT(*) AS c FROM approvals WHERE status='request_info'"
            ).fetchone()["c"]
            if total
            else 0,
            "avg_tasks_per_completed_case": self._avg_tasks_per_completed_case(total=total),
            "eval_pass_rate": (int(pass_count) / max(1, len(eval_summary))) * 100
            if eval_summary
            else 0.0,
        }

    def _avg_tasks_per_completed_case(self, total: int) -> float:
        with self._connect() as conn:
            total_tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        completed = (
            conn.execute("SELECT COUNT(*) AS c FROM cases WHERE state='completed'").fetchone()["c"]
            if total
            else 0
        )
        if completed == 0:
            return 0.0
        return float(total_tasks) / float(completed)

    def get_case_full_snapshot(self, case_id: str) -> dict[str, Any] | None:
        case_row = None
        with self._connect() as conn:
            case_row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if not case_row:
                return None
            raw_payload = _from_json(case_row["raw_payload"]) or {}
            normalized_payload = _from_json(case_row["normalized_payload"]) or None
            routing = self.get_routing_decision(case_id)
            approval = self.get_approval_by_case(case_id)
            findings = self.find_case_findings(case_id)
            brief = self.get_brief(case_id)
            tasks = self.list_tasks(case_id)
            traces = self.list_traces(case_id)

        return {
            "case": IntakePackage.model_validate(raw_payload),
            "normalized": NormalizedCase.model_validate(normalized_payload)
            if normalized_payload
            else None,
            "findings": findings,
            "routing": routing,
            "approval": approval,
            "brief": brief,
            "tasks": tasks,
            "traces": traces,
            "state": case_row["state"],
            "route": case_row["final_route"],
        }

    def get_kpi(self, case_id: str) -> KPIRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM kpi_records WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            return None
        return KPIRecord(
            case_id=row["case_id"],
            final_route=row["final_route"],
            straight_through=bool(row["straight_through"]),
            approval_required=bool(row["approval_required"]),
            reviewer_override=bool(row["reviewer_override"]),
            processing_time_ms=row["processing_time_ms"],
            generated_task_count=row["generated_task_count"],
        )
