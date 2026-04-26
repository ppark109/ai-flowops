from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from schemas.case import (
    Approval,
    ApprovalStatus,
    CaseWorkflowState,
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


def _default_db_path() -> Path:
    return Path("data/runtime/app.sqlite3")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(payload: object) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(mode="json"), default=str)
    return json.dumps(payload, default=str)


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


class WorkflowStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._lock = Lock()
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS cases (
              case_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              intake_payload TEXT NOT NULL,
              normalized_payload TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
              document_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              document_payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS findings (
              finding_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              finding_payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS routing_decisions (
              case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
              routing_payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
              approval_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              approval_payload TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(case_id, approval_id)
            );

            CREATE TABLE IF NOT EXISTS generated_outputs (
              output_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              output_type TEXT NOT NULL,
              output_payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
              task_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              task_payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trace_records (
              trace_id TEXT PRIMARY KEY,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              step_name TEXT NOT NULL,
              agent_name TEXT NOT NULL,
              model_provider_label TEXT NOT NULL,
              inputs_summary TEXT NOT NULL,
              outputs_summary TEXT NOT NULL,
              latency_ms INTEGER NOT NULL,
              token_count INTEGER NOT NULL,
              cost_usd REAL NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS eval_results (
              eval_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
              result_payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kpi_records (
              case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
              final_route TEXT NOT NULL,
              straight_through INTEGER NOT NULL,
              approval_required INTEGER NOT NULL,
              reviewer_override INTEGER NOT NULL,
              processing_time_ms INTEGER,
              generated_task_count INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def clear(self) -> None:
        for table in [
            "trace_records",
            "findings",
            "routing_decisions",
            "approvals",
            "generated_outputs",
            "tasks",
            "documents",
            "eval_results",
            "kpi_records",
            "cases",
        ]:
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()

    def upsert_case(self, intake: IntakePackage, status: str = "draft") -> None:
        now = _now()
        self.conn.execute(
            """
            INSERT INTO cases(case_id, status, intake_payload, normalized_payload, created_at, updated_at)
            VALUES (?, ?, ?, NULL, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
              status = excluded.status,
              intake_payload = excluded.intake_payload,
              updated_at = excluded.updated_at
            """,
            (intake.case_id, status, _serialize(intake), now, now),
        )
        self.conn.commit()

    def list_cases(self, *, status: str | None = None) -> list[dict[str, object]]:
        where = "WHERE status = ?" if status else ""
        args: tuple[str, ...] = (status,) if status else tuple()
        rows = self.conn.execute(
            f"""
            SELECT cases.case_id, cases.status, cases.intake_payload, cases.normalized_payload,
                   routing_decisions.routing_payload
            FROM cases
            LEFT JOIN routing_decisions ON routing_decisions.case_id = cases.case_id
            {where}
            ORDER BY cases.case_id
            """,
            args,
        ).fetchall()
        output: list[dict[str, object]] = []
        for row in rows:
            intake_payload = json.loads(row["intake_payload"])
            normalized = (
                json.loads(row["normalized_payload"]) if row["normalized_payload"] else None
            )
            routing = json.loads(row["routing_payload"]) if row["routing_payload"] else None
            output.append(
                {
                    "case_id": row["case_id"],
                    "status": row["status"],
                    "customer_name": intake_payload["customer_name"],
                    "account_name": intake_payload.get("account_name"),
                    "actual_route": routing.get("recommended_route") if routing else None,
                    "expected_route": intake_payload.get("expected_route"),
                    "expected_approval_required": intake_payload.get("expected_approval_required"),
                    "package_complete": normalized.get("package_complete") if normalized else None,
                }
            )
        return output

    def get_status(self, case_id: str) -> str:
        row = self.conn.execute("SELECT status FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        return row["status"]

    def set_status(self, case_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?",
            (status, _now(), case_id),
        )
        self.conn.commit()

    def get_intake(self, case_id: str) -> IntakePackage | SeedCase:
        row = self.conn.execute(
            "SELECT intake_payload FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        data = json.loads(row["intake_payload"])
        return IntakePackage.model_validate(data)

    def save_normalized_case(self, case_id: str, normalized: NormalizedCase) -> None:
        now = _now()
        self.conn.execute(
            """
            INSERT INTO cases (case_id, status, intake_payload, normalized_payload, created_at, updated_at)
            VALUES ((SELECT case_id FROM cases WHERE case_id = ?), (SELECT status FROM cases WHERE case_id = ?), 
                    (SELECT intake_payload FROM cases WHERE case_id = ?), ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
              normalized_payload = excluded.normalized_payload,
              updated_at = excluded.updated_at
            """,
            (case_id, case_id, case_id, _serialize(normalized), now, now),
        )
        self.conn.execute("DELETE FROM documents WHERE case_id = ?", (case_id,))
        for document in normalized.document_refs:
            self.conn.execute(
                "INSERT INTO documents(document_id, case_id, document_payload) VALUES (?, ?, ?)",
                (document.document_id, case_id, _serialize(document)),
            )
        self.conn.commit()

    def get_normalized_case(self, case_id: str) -> NormalizedCase | None:
        row = self.conn.execute(
            "SELECT normalized_payload FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None or row["normalized_payload"] is None:
            return None
        return NormalizedCase.model_validate(json.loads(row["normalized_payload"]))

    def save_findings(self, case_id: str, findings: Sequence[Finding]) -> None:
        self.conn.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
        for finding in findings:
            self.conn.execute(
                "INSERT INTO findings(finding_id, case_id, finding_payload) VALUES (?, ?, ?)",
                (finding.finding_id, case_id, _serialize(finding)),
            )
        self.conn.commit()

    def get_findings(self, case_id: str) -> list[Finding]:
        rows = self.conn.execute(
            "SELECT finding_payload FROM findings WHERE case_id = ? ORDER BY finding_id", (case_id,)
        ).fetchall()
        return [Finding.model_validate(json.loads(row["finding_payload"])) for row in rows]

    def save_routing_decision(self, case_id: str, decision: RoutingDecision) -> None:
        self.conn.execute(
            """
            INSERT INTO routing_decisions(case_id, routing_payload) VALUES (?, ?)
            ON CONFLICT(case_id) DO UPDATE SET routing_payload = excluded.routing_payload
            """,
            (case_id, _serialize(decision)),
        )
        self.conn.commit()

    def get_routing_decision(self, case_id: str) -> RoutingDecision | None:
        row = self.conn.execute(
            "SELECT routing_payload FROM routing_decisions WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        return RoutingDecision.model_validate(json.loads(row["routing_payload"]))

    def save_approval(self, case_id: str, approval: Approval) -> None:
        now = approval.created_at or datetime.now(UTC)
        self.conn.execute(
            """
            INSERT INTO approvals(approval_id, case_id, approval_payload, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(approval_id) DO UPDATE SET
              approval_payload = excluded.approval_payload
            """,
            (approval.approval_id, case_id, _serialize(approval), now.isoformat()),
        )
        self.conn.commit()

    def get_approval(self, case_id: str) -> Approval | None:
        row = self.conn.execute(
            "SELECT approval_payload FROM approvals WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        ).fetchone()
        if row is None:
            return None
        return Approval.model_validate(json.loads(row["approval_payload"]))

    def get_approval_by_id(self, approval_id: str) -> Approval | None:
        row = self.conn.execute(
            "SELECT approval_payload FROM approvals WHERE approval_id = ?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        return Approval.model_validate(json.loads(row["approval_payload"]))

    def remove_approval(self, case_id: str) -> None:
        self.conn.execute("DELETE FROM approvals WHERE case_id = ?", (case_id,))
        self.conn.commit()

    def list_approvals(self, status_filter: ApprovalStatus | None = None) -> list[Approval]:
        if status_filter is None:
            query = "SELECT approval_payload FROM approvals ORDER BY created_at DESC"
            rows = self.conn.execute(query).fetchall()
        else:
            query = """
            SELECT approval_payload FROM approvals
            WHERE json_extract(approval_payload, '$.status') = ?
            ORDER BY created_at DESC
            """
            rows = self.conn.execute(query, (status_filter,)).fetchall()
        return [Approval.model_validate(json.loads(row["approval_payload"])) for row in rows]

    def list_pending_approvals(self) -> list[Approval]:
        return [
            approval
            for approval in self.list_approvals()
            if approval.status in {"pending", "request_info"}
        ]

    def save_brief(self, case_id: str, brief: GeneratedBrief) -> None:
        self.conn.execute(
            """
            INSERT INTO generated_outputs(output_id, case_id, output_type, output_payload, created_at)
            VALUES (?, ?, 'brief', ?, ?)
            """,
            (_uid("brief"), case_id, _serialize(brief), _now()),
        )
        self.conn.commit()

    def get_brief(self, case_id: str) -> GeneratedBrief | None:
        row = self.conn.execute(
            """
            SELECT output_payload FROM generated_outputs
            WHERE case_id = ? AND output_type='brief'
            ORDER BY output_id DESC LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        if row is None:
            return None
        return GeneratedBrief.model_validate(json.loads(row["output_payload"]))

    def save_tasks(self, case_id: str, tasks: list[GeneratedTask]) -> None:
        self.conn.execute("DELETE FROM tasks WHERE case_id = ?", (case_id,))
        for task in tasks:
            self.conn.execute(
                "INSERT INTO tasks(task_id, case_id, task_payload) VALUES (?, ?, ?)",
                (task.task_id, case_id, _serialize(task)),
            )
        self.conn.commit()

    def get_tasks(self, case_id: str) -> list[GeneratedTask]:
        rows = self.conn.execute(
            "SELECT task_payload FROM tasks WHERE case_id = ? ORDER BY task_id", (case_id,)
        ).fetchall()
        return [GeneratedTask.model_validate(json.loads(row["task_payload"])) for row in rows]

    def get_kpi_summary(self) -> dict[str, object]:
        kpis = self.get_kpis()
        case_rows = self.conn.execute("SELECT case_id, status FROM cases").fetchall()
        total_cases = len(case_rows)
        status_by_case = {row["case_id"]: row["status"] for row in case_rows}
        if total_cases == 0:
            return {
                "total_cases": 0,
                "straight_through_count": 0,
                "escalation_count": 0,
                "override_count": 0,
                "rejected_count": 0,
                "request_info_count": 0,
                "avg_tasks": 0.0,
                "pending_approvals": 0,
                "route_distribution": {
                    route: 0
                    for route in ("auto_approve", "legal", "security", "implementation", "finance")
                },
            }

        route_dist: dict[str, int] = {
            route: 0 for route in ("auto_approve", "legal", "security", "implementation", "finance")
        }
        for row in kpis:
            route_dist[row.final_route] = route_dist.get(row.final_route, 0) + 1
        straight = sum(1 for row in kpis if row.straight_through)
        escalations = sum(1 for row in kpis if row.approval_required)
        overrides = sum(1 for row in kpis if row.reviewer_override)
        completed_kpis = [
            row
            for row in kpis
            if status_by_case.get(row.case_id) in {"approved", "completed"}
        ]
        avg_tasks = (
            sum(row.generated_task_count for row in completed_kpis) / len(completed_kpis)
            if completed_kpis
            else 0.0
        )
        approvals_rows = self.list_approvals()
        pending_approvals = len([item for item in approvals_rows if item.status == "pending"])
        rejected_count = len([item for item in approvals_rows if item.status == "rejected"])
        request_info_count = len([item for item in approvals_rows if item.status == "request_info"])
        return {
            "total_cases": total_cases,
            "straight_through_count": straight,
            "escalation_count": escalations,
            "override_count": overrides,
            "rejected_count": rejected_count,
            "request_info_count": request_info_count,
            "avg_tasks": avg_tasks,
            "pending_approvals": pending_approvals,
            "route_distribution": route_dist,
        }

    def save_traces(self, traces: Iterable[TraceRecord]) -> None:
        for trace in traces:
            self.conn.execute(
                """
                INSERT INTO trace_records(
                  trace_id, case_id, step_name, agent_name, model_provider_label,
                  inputs_summary, outputs_summary, latency_ms, token_count, cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _uid("trace"),
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
        self.conn.commit()

    def get_traces(self, case_id: str) -> list[TraceRecord]:
        rows = self.conn.execute(
            "SELECT * FROM trace_records WHERE case_id = ? ORDER BY created_at ASC, trace_id ASC",
            (case_id,),
        ).fetchall()
        return [
            TraceRecord.model_validate(
                {
                    "case_id": row["case_id"],
                    "step_name": row["step_name"],
                    "agent_name": row["agent_name"],
                    "model_provider_label": row["model_provider_label"],
                    "inputs_summary": row["inputs_summary"],
                    "outputs_summary": row["outputs_summary"],
                    "latency_ms": row["latency_ms"],
                    "token_count": row["token_count"],
                    "cost_usd": row["cost_usd"],
                    "created_at": row["created_at"],
                }
            )
            for row in rows
        ]

    def save_kpi(self, kpi: KPIRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO kpi_records(
              case_id, final_route, straight_through, approval_required,
              reviewer_override, processing_time_ms, generated_task_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
              final_route = excluded.final_route,
              straight_through = excluded.straight_through,
              approval_required = excluded.approval_required,
              reviewer_override = excluded.reviewer_override,
              processing_time_ms = excluded.processing_time_ms,
              generated_task_count = excluded.generated_task_count,
              created_at = excluded.created_at
            """,
            (
                kpi.case_id,
                kpi.final_route,
                1 if kpi.straight_through else 0,
                1 if kpi.approval_required else 0,
                1 if kpi.reviewer_override else 0,
                kpi.processing_time_ms,
                kpi.generated_task_count,
                _now(),
            ),
        )
        self.conn.commit()

    def get_kpis(self) -> list[KPIRecord]:
        rows = self.conn.execute("SELECT * FROM kpi_records ORDER BY case_id").fetchall()
        return [
            KPIRecord(
                case_id=row["case_id"],
                final_route=row["final_route"],
                straight_through=bool(row["straight_through"]),
                approval_required=bool(row["approval_required"]),
                reviewer_override=bool(row["reviewer_override"]),
                processing_time_ms=row["processing_time_ms"],
                generated_task_count=row["generated_task_count"],
            )
            for row in rows
        ]

    def save_eval_result(self, run_id: str, result: EvalResult) -> None:
        self.conn.execute(
            "INSERT INTO eval_results(eval_id, run_id, case_id, result_payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (_uid("eval"), run_id, result.case_id, _serialize(result), _now()),
        )
        self.conn.commit()

    def get_eval_results(self, case_id: str | None = None) -> list[EvalResult]:
        if case_id is None:
            rows = self.conn.execute(
                "SELECT result_payload FROM eval_results ORDER BY eval_id"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT result_payload FROM eval_results WHERE case_id = ? ORDER BY eval_id",
                (case_id,),
            ).fetchall()
        return [EvalResult.model_validate(json.loads(row["result_payload"])) for row in rows]

    def get_eval_summary(self, run_id: str | None = None) -> dict[str, float]:
        where = ""
        args: tuple[str, ...] = tuple()
        if run_id is not None:
            where = "WHERE run_id = ?"
            args = (run_id,)

        rows = self.conn.execute(
            f"SELECT result_payload FROM eval_results {where} ORDER BY eval_id",
            args,
        ).fetchall()
        summary: dict[str, int | float] = {
            "total": 0,
            "route_pass": 0,
            "approval_pass": 0,
            "grounding_pass": 0,
            "brief_pass": 0,
            "total_pass": 0,
        }
        for row in rows:
            payload = json.loads(row["result_payload"])
            summary["total"] += 1
            route_pass = bool(payload.get("route_pass"))
            approval_pass = bool(payload.get("approval_pass"))
            grounding_pass = bool(payload.get("grounding_pass"))
            brief_pass = bool(payload.get("brief_completeness_pass"))
            summary["route_pass"] += int(route_pass)
            summary["approval_pass"] += int(approval_pass)
            summary["grounding_pass"] += int(grounding_pass)
            summary["brief_pass"] += int(brief_pass)
            summary["total_pass"] += int(
                route_pass and approval_pass and grounding_pass and brief_pass
            )
        total = float(summary["total"])
        if total == 0:
            return {
                key: 0.0
                for key in (
                    "total_rate",
                    "route_rate",
                    "approval_rate",
                    "grounding_rate",
                    "brief_rate",
                )
            }
        return {
            "total_rate": summary["total_pass"] / total,
            "route_rate": summary["route_pass"] / total,
            "approval_rate": summary["approval_pass"] / total,
            "grounding_rate": summary["grounding_pass"] / total,
            "brief_rate": summary["brief_pass"] / total,
        }

    def get_case_state(self, case_id: str) -> CaseWorkflowState:
        intake = self.get_intake(case_id)
        state = self.get_status(case_id)
        normalized = self.get_normalized_case(case_id)
        if normalized is None:
            normalized = NormalizedCase(
                case_id=intake.case_id,
                customer_name=intake.customer_name,
                package_complete=True,
            )

        return CaseWorkflowState(
            case_id=case_id,
            state=state,
            intake=intake,
            normalized_case=normalized,
            findings=self.get_findings(case_id),
            routing_decision=self.get_routing_decision(case_id),
            approval=self.get_approval(case_id),
            brief=self.get_brief(case_id),
            tasks=self.get_tasks(case_id),
            traces=self.get_traces(case_id),
        )
