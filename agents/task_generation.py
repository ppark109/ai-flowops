from __future__ import annotations

import time
from uuid import uuid4

from agents.base import build_trace
from schemas.case import Finding, GeneratedTask, IntakePackage, RoutingDecision, TraceRecord


class TaskGenerationAgent:
    provider_label = "deterministic-fallback"

    def run(
        self,
        intake: IntakePackage,
        routing: RoutingDecision,
        findings: list[Finding],
    ) -> tuple[list[GeneratedTask], TraceRecord]:
        start = time.perf_counter()
        route = routing.recommended_route
        route_tasks = _route_task_specs(route, intake.expected_task_owner_category)

        if not routing.approval_required:
            owner = route_tasks["owner"]
            tasks = [
                GeneratedTask(
                    task_id=f"task-{uuid4().hex[:8]}",
                    title=route_tasks["title"],
                    owner_function=owner,
                    priority="medium",
                    due_category="day_1",
                    source_finding_ids=[f.finding_id for f in findings],
                    evidence_references=[e.quote for f in findings for e in f.evidence[:1]],
                )
            ]
            trace = build_trace(
                case_id=intake.case_id,
                step_name="task_generation",
                agent_name="TaskGenerationAgent",
                inputs_summary=f"findings={len(findings)}",
                outputs_summary=f"tasks={len(tasks)}",
                start_time=start,
            )
            return tasks, trace

        return [], build_trace(
            case_id=intake.case_id,
            step_name="task_generation",
            agent_name="TaskGenerationAgent",
            inputs_summary=f"findings={len(findings)}",
            outputs_summary="tasks=0 approval_required",
            start_time=start,
        )


def _route_task_specs(route: str, owner_hint: str | None) -> dict[str, str]:
    if route == "legal":
        return {
            "title": "Run legal review on flagged clauses",
            "owner": owner_hint or "legal",
        }
    if route == "security":
        return {
            "title": "Review security artifacts and residency/DPA requirements",
            "owner": owner_hint or "security",
        }
    if route == "implementation":
        return {
            "title": "Validate implementation plan, dependencies, and owner alignment",
            "owner": owner_hint or "implementation",
        }
    if route == "finance":
        return {
            "title": "Review finance exceptions and finalize commercial terms",
            "owner": owner_hint or "finance",
        }
    return {
        "title": "Prepare onboarding checklist and rollout runbook",
        "owner": owner_hint or "commercial_ops",
    }
