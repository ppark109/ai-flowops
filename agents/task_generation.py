from __future__ import annotations

import time
import uuid

from agents.base import build_trace
from schemas.case import Finding, GeneratedTask, RoutingDecision, TraceRecord


class TaskGenerationAgent:
    provider_label = "deterministic-fallback"

    def run(
        self, case_id: str, routing_decision: RoutingDecision, findings: list[Finding]
    ) -> tuple[list[GeneratedTask], TraceRecord]:
        start = time.perf_counter()
        route = routing_decision.recommended_route

        owner, tasks = _route_defaults(route)
        task_rows: list[GeneratedTask] = []
        for idx, (title, due) in enumerate(tasks, start=1):
            finding_ids = [f.finding_id for f in findings if f.route == route]
            evidence_refs = [f.rule_id for f in findings if f.route == route][:3]
            task_rows.append(
                GeneratedTask(
                    task_id=f"task-{uuid.uuid4().hex[:10]}",
                    case_id=case_id,
                    title=title,
                    owner_function=owner,
                    priority="high" if route != "auto_approve" else "medium",
                    due_category=due,
                    source_finding_ids=finding_ids,
                    evidence_references=evidence_refs,
                    status="open",
                )
            )
            if idx >= 3:
                break

        if not task_rows:
            task_rows.append(
                GeneratedTask(
                    task_id=f"task-{uuid.uuid4().hex[:10]}",
                    case_id=case_id,
                    title=f"Prepare {route.replace('_', ' ')} handoff",
                    owner_function=owner,
                    priority="medium",
                    due_category="t+24h",
                    source_finding_ids=[],
                    evidence_references=[],
                    status="open",
                )
            )

        trace = build_trace(
            case_id=case_id,
            step_name="task_generation",
            agent_name="TaskGenerationAgent",
            inputs_summary=f"route={route}",
            outputs_summary=f"tasks={len(task_rows)}",
            start_time=start,
            model_provider_label=self.provider_label,
        )
        return task_rows, trace


def _route_defaults(route: str) -> tuple[str, list[tuple[str, str]]]:
    if route == "legal":
        return (
            "legal",
            [
                ("Review nonstandard legal terms", "same_day"),
                ("Align indemnity and liability language", "same_week"),
            ],
        )
    if route == "security":
        return (
            "security",
            [
                ("Collect DPA and security attestations", "same_day"),
                ("Review residency and hosting constraints", "same_week"),
            ],
        )
    if route == "implementation":
        return (
            "implementation",
            [
                ("Assign implementation owner", "same_day"),
                ("Confirm go-live plan and dependencies", "same_week"),
            ],
        )
    if route == "finance":
        return (
            "finance",
            [
                ("Validate commercial exception", "same_day"),
                ("Review rebate/penalty exposure", "same_week"),
            ],
        )
    return (
        "operations",
        [
            ("Create onboarding checklist", "same_day"),
            ("Complete account setup", "same_week"),
        ],
    )
