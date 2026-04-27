from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.case import EvalResult
from workflows.orchestrator import WorkflowOrchestrator
from workflows.playbook import load_default_playbook
from workflows.seeding import load_held_out_cases
from workflows.storage import WorkflowStorage


def main() -> None:
    storage = WorkflowStorage("data/runtime/app.sqlite3")
    orchestrator = WorkflowOrchestrator(storage, load_default_playbook())
    cases = load_held_out_cases("data/held_out/cases")
    results: list[EvalResult] = []

    for case in cases:
        storage.upsert_case(case, state="draft")
        snapshot = orchestrator.run_case(case)
        decision = snapshot.routing_decision
        if not decision:
            raise RuntimeError(f"no routing decision for {case.case_id}")
        result = EvalResult(
            case_id=case.case_id,
            expected_route=case.expected_route,
            actual_route=decision.recommended_route,
            route_pass=decision.recommended_route == case.expected_route,
            grounding_pass=bool(snapshot.findings) or not case.expected_approval_required,
            approval_pass=decision.approval_required == case.expected_approval_required,
            brief_completeness_pass=bool(snapshot.brief) or decision.approval_required,
            notes=None,
        )
        storage.save_eval_result(result)
        results.append(result)

    pass_count = sum(
        1
        for result in results
        if result.route_pass
        and result.grounding_pass
        and result.approval_pass
        and result.brief_completeness_pass
    )
    print(f"evals={len(results)} pass_count={pass_count}")


if __name__ == "__main__":
    main()
