from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.guided_demo import (
    CASE_ID,
    get_case_room_context,
    get_department_detail_context,
    get_document_context,
    get_document_package_context,
    get_evidence_map_context,
    get_kpi_context,
    get_source_document_context,
    get_walkthrough_context,
)
from schemas.case import (
    ApprovalStatus,
    EvalResult,
    IntakePackage,
    RoutingDecision,
    WorkflowCaseQuery,
)
from workflows import load_default_playbook, validate_playbook
from workflows.orchestrator import WorkflowOrchestrator
from workflows.routing import ROUTES
from workflows.seeding import load_held_out_cases, load_seed_cases, seed_database
from workflows.storage import WorkflowStorage

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_storage(request: Request) -> WorkflowStorage:
    return request.app.state.storage


def get_orchestrator(request: Request) -> WorkflowOrchestrator:
    return request.app.state.orchestrator


STORAGE_DEPENDENCY = Depends(get_storage)
ORCHESTRATOR_DEPENDENCY = Depends(get_orchestrator)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta")
def meta() -> dict[str, object]:
    return {"workflow": "ai-flowops", "routes": list(ROUTES)}


@router.get("/api/cases")
def api_list_cases(
    request: Request,
    route: str | None = None,
    state: str | None = None,
    search: str | None = None,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
) -> list[dict[str, Any]]:
    query = WorkflowCaseQuery(route=route, state=state, search=search)
    items = storage.list_cases(route=query.route, state=query.state, search=query.search)
    return [item.__dict__ for item in items]


@router.post("/api/cases/seed")
def api_seed_cases(
    wipe: bool = True,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
) -> dict[str, int]:
    seeded = seed_database(storage, folder="data/seed/cases", wipe=wipe)
    return {"seeded": len(seeded)}


@router.post("/api/cases")
def api_create_case(
    payload: dict[str, Any],
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
) -> dict[str, str]:
    case = IntakePackage.model_validate(payload)
    storage.upsert_case(case, state="draft")
    return {"case_id": case.case_id}


@router.get("/api/cases/{case_id}")
def api_case_detail(
    case_id: str,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
) -> dict[str, Any]:
    snapshot = storage.get_case_full_snapshot(case_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "state": snapshot["state"],
        "case": snapshot["case"].model_dump(),
        "normalized_case": snapshot["normalized"].model_dump() if snapshot["normalized"] else None,
        "findings": [f.model_dump() for f in snapshot["findings"]],
        "routing_decision": snapshot["routing"].model_dump() if snapshot["routing"] else None,
        "approval": snapshot["approval"].model_dump() if snapshot["approval"] else None,
        "brief": snapshot["brief"].model_dump() if snapshot["brief"] else None,
        "tasks": [t.model_dump() for t in snapshot["tasks"]],
        "traces": [t.model_dump() for t in snapshot["traces"]],
    }


@router.post("/api/cases/{case_id}/run")
def api_run_case(
    case_id: str,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    case = storage.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    result = orchestrator.run_case(case)
    return result.model_dump()


@router.get("/api/approvals")
def api_list_approvals(
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
    status: ApprovalStatus | None = None,
) -> list[dict[str, Any]]:
    approvals = storage.list_approvals(status=status)
    return [approval.model_dump() for approval in approvals]


@router.post("/api/approvals/{approval_id}/approve")
def api_approve_case(
    approval_id: str,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    return orchestrator.approve(approval_id=approval_id).model_dump()


@router.post("/api/approvals/{approval_id}/reject")
def api_reject_case(
    approval_id: str,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    return orchestrator.reject(approval_id=approval_id).model_dump()


@router.post("/api/approvals/{approval_id}/override")
def api_override_case(
    approval_id: str,
    route: str,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    if route not in ROUTES:
        raise HTTPException(status_code=400, detail="Invalid route override")
    return orchestrator.override_route(approval_id=approval_id, route=route).model_dump()


@router.post("/api/approvals/{approval_id}/request-info")
def api_request_info_case(
    approval_id: str,
    request_info: str,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    return orchestrator.request_info(
        approval_id=approval_id, requested_info=request_info
    ).model_dump()


@router.get("/api/kpis")
def api_kpis(storage: WorkflowStorage = STORAGE_DEPENDENCY) -> dict[str, Any]:
    return storage.compute_kpi_summary()


@router.get("/api/evals")
def api_list_evals(storage: WorkflowStorage = STORAGE_DEPENDENCY) -> dict[str, Any]:
    evals = storage.list_eval_results()
    pass_count = sum(
        1
        for item in evals
        if item.route_pass
        and item.approval_pass
        and item.grounding_pass
        and item.brief_completeness_pass
    )
    return {
        "results": [result.model_dump() for result in evals],
        "summary": {
            "total": len(evals),
            "pass_count": pass_count,
        },
    }


@router.post("/api/evals/run")
def api_run_evals(
    include_seed: bool = False,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
) -> dict[str, Any]:
    cases = load_held_out_cases("data/held_out/cases")
    if include_seed:
        cases.extend(load_seed_cases("data/seed/cases"))
    evals: list[EvalResult] = []
    for case in cases:
        result_snapshot = orchestrator.run_case(case)
        decision = result_snapshot.routing_decision
        if not decision:
            raise HTTPException(status_code=400, detail=f"no routing decision for {case.case_id}")
        eval_result = _evaluate_case_output(
            case.expected_route, case.expected_approval_required, decision, result_snapshot
        )
        storage.save_eval_result(eval_result)
        evals.append(eval_result)
    return {"count": len(evals), "results": [e.model_dump() for e in evals]}


@router.get("/api/traces/{case_id}")
def api_case_traces(
    case_id: str, storage: WorkflowStorage = STORAGE_DEPENDENCY
) -> list[dict[str, Any]]:
    traces = storage.list_traces(case_id)
    if not traces:
        raise HTTPException(status_code=404, detail="No traces found")
    return [trace.model_dump() for trace in traces]


@router.get("/", response_class=HTMLResponse)
def page_demo_home(request: Request):
    return templates.TemplateResponse(request, "demo_overview.html", get_case_room_context())


@router.get("/demo", response_class=HTMLResponse)
def page_demo(request: Request):
    return templates.TemplateResponse(request, "demo_overview.html", get_case_room_context())


@router.get("/demo/cases")
def page_demo_cases():
    return RedirectResponse(url=f"/demo/cases/{CASE_ID}?step=extraction", status_code=307)


@router.get("/demo/cases/{case_id}", response_class=HTMLResponse)
def page_demo_case(request: Request, case_id: str, step: str | None = None):
    if case_id != CASE_ID:
        raise HTTPException(status_code=404, detail="Demo case not found")
    return templates.TemplateResponse(request, "demo_case.html", get_walkthrough_context(step=step))


@router.get("/demo/evidence-map", response_class=HTMLResponse)
def page_demo_evidence_map(
    request: Request,
    department: str | None = None,
    risks_only: bool = False,
):
    return templates.TemplateResponse(
        request,
        "demo_evidence_map.html",
        get_evidence_map_context(department=department, risks_only=risks_only),
    )


@router.get("/demo/source-document", response_class=HTMLResponse)
def page_demo_source_document(request: Request, active: str | None = None):
    return templates.TemplateResponse(
        request,
        "demo_source_document.html",
        get_source_document_context(active=active),
    )


@router.get("/demo/document-package", response_class=HTMLResponse)
def page_demo_document_package(request: Request):
    return templates.TemplateResponse(
        request,
        "demo_document_package.html",
        get_document_package_context(),
    )


@router.get("/demo/document/{document_id}", response_class=HTMLResponse)
def page_demo_document(request: Request, document_id: str):
    try:
        context = get_document_context(document_id=document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    return templates.TemplateResponse(request, "demo_document.html", context)


@router.get("/demo/department-packet", response_class=HTMLResponse)
def page_demo_department_packet(request: Request, department: str | None = None):
    return templates.TemplateResponse(
        request,
        "demo_department_packet.html",
        get_department_detail_context(department_id=department),
    )


@router.get("/demo/kpis", response_class=HTMLResponse)
def page_demo_kpis(request: Request):
    return templates.TemplateResponse(request, "demo_kpi_dashboard.html", get_kpi_context())


@router.get("/demo/architecture", response_class=HTMLResponse)
def page_demo_architecture(request: Request):
    return templates.TemplateResponse(request, "demo_architecture.html", get_case_room_context())


@router.get("/technical-dashboard", response_class=HTMLResponse)
def page_dashboard(request: Request, storage: WorkflowStorage = STORAGE_DEPENDENCY):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"summary": storage.compute_kpi_summary()},
    )


@router.get("/cases", response_class=HTMLResponse)
def page_cases(
    request: Request,
    route: str | None = None,
    state: str | None = None,
    search: str | None = None,
    storage: WorkflowStorage = STORAGE_DEPENDENCY,
):
    items = storage.list_cases(route=route, state=state, search=search)
    return templates.TemplateResponse(
        request,
        "cases.html",
        {
            "cases": [item.__dict__ for item in items],
            "route": route,
            "state": state,
            "search": search,
        },
    )


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def page_case_detail(request: Request, case_id: str, storage: WorkflowStorage = STORAGE_DEPENDENCY):
    snapshot = storage.get_case_full_snapshot(case_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Case not found")
    return templates.TemplateResponse(
        request,
        "case_detail.html",
        {
            "case": snapshot["case"],
            "normalized": snapshot["normalized"],
            "state": snapshot["state"],
            "findings": snapshot["findings"],
            "routing": snapshot["routing"],
            "approval": snapshot["approval"],
            "brief": snapshot["brief"],
            "tasks": snapshot["tasks"],
            "traces": snapshot["traces"],
        },
    )


@router.get("/approvals", response_class=HTMLResponse)
def page_approvals(request: Request, storage: WorkflowStorage = STORAGE_DEPENDENCY):
    return templates.TemplateResponse(
        request,
        "approvals.html",
        {"approvals": storage.list_approvals(status="pending")},
    )


@router.get("/approvals/{approval_id}", response_class=HTMLResponse)
def page_approval_detail(
    request: Request, approval_id: str, storage: WorkflowStorage = STORAGE_DEPENDENCY
):
    approval = _require_approval(storage, approval_id)
    snapshot = storage.get_case_full_snapshot(approval.case_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Case not found")
    return templates.TemplateResponse(
        request,
        "approval_detail.html",
        {
            "approval": approval,
            "case": snapshot["case"],
            "findings": snapshot["findings"],
            "routing": snapshot["routing"],
        },
    )


@router.post("/approvals/{approval_id}/action")
def page_approval_action(
    request: Request,
    approval_id: str,
    action: str = Form(...),
    route: str = Form(""),
    reviewer: str | None = Form(None),
    comments: str | None = Form(None),
    requested_info: str | None = Form(None),
    orchestrator: WorkflowOrchestrator = ORCHESTRATOR_DEPENDENCY,
):
    if action == "approve":
        orchestrator.approve(approval_id=approval_id, reviewer=reviewer, comments=comments)
    elif action == "reject":
        orchestrator.reject(approval_id=approval_id, reviewer=reviewer, comments=comments)
    elif action == "request-info":
        orchestrator.request_info(
            approval_id=approval_id,
            reviewer=reviewer,
            comments=comments,
            requested_info=requested_info,
        )
    elif action == "override":
        if route not in ROUTES:
            raise HTTPException(status_code=400, detail="invalid route")
        orchestrator.override_route(
            approval_id=approval_id, route=route, reviewer=reviewer, comments=comments
        )
    else:
        raise HTTPException(status_code=400, detail="invalid action")
    return templates.TemplateResponse(request, "status_refresh.html")


@router.get("/evals", response_class=HTMLResponse)
def page_evals(request: Request, storage: WorkflowStorage = STORAGE_DEPENDENCY):
    evals = storage.list_eval_results()
    pass_count = sum(
        1
        for e in evals
        if e.route_pass and e.approval_pass and e.grounding_pass and e.brief_completeness_pass
    )
    return templates.TemplateResponse(
        request,
        "evals.html",
        {"evals": evals, "pass_count": pass_count, "total": len(evals)},
    )


@router.get("/kpis", response_class=HTMLResponse)
def page_kpis(request: Request, storage: WorkflowStorage = STORAGE_DEPENDENCY):
    return templates.TemplateResponse(
        request, "kpis.html", {"summary": storage.compute_kpi_summary()}
    )


@router.get("/playbook", response_class=HTMLResponse)
def page_playbook(request: Request):
    playbook = load_default_playbook()
    validate_playbook(playbook)
    return templates.TemplateResponse(request, "playbook.html", {"playbook": playbook})


def _require_approval(storage: WorkflowStorage, approval_id: str):
    approvals = storage.list_approvals()
    for approval in approvals:
        if approval.approval_id == approval_id:
            return approval
    raise HTTPException(status_code=404, detail="Approval not found")


def _evaluate_case_output(
    expected_route: str,
    expected_approval_required: bool,
    decision: RoutingDecision,
    snapshot,
) -> EvalResult:
    route_pass = decision.recommended_route == expected_route
    approval_pass = decision.approval_required == expected_approval_required
    grounding_pass = bool(snapshot.findings) or not expected_approval_required
    brief_pass = bool(snapshot.brief) or decision.approval_required
    return EvalResult(
        case_id=snapshot.case_id,
        expected_route=expected_route,
        actual_route=decision.recommended_route,
        route_pass=route_pass,
        grounding_pass=grounding_pass,
        approval_pass=approval_pass,
        brief_completeness_pass=brief_pass,
        notes=None,
    )
