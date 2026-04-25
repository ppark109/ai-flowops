from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from schemas.case import IntakePackage, Route
from workflows.orchestrator import WorkflowOrchestrator
from workflows.routing import ROUTES
from workflows.seeding import seed_cases

router = APIRouter()


class ApprovalPayload(BaseModel):
    reviewer: str | None = None
    comments: str | None = None


class ApprovalPayloadRequiredComment(BaseModel):
    reviewer: str
    comments: str


class OverridePayload(ApprovalPayloadRequiredComment):
    route: Route


def _orchestrator(request: Request) -> WorkflowOrchestrator:
    return request.app.state.orchestrator


def _templates(request: Request):
    return request.app.state.templates


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta")
def meta() -> dict[str, object]:
    return {
        "workflow": "commercial_intake_to_operational_handoff",
        "routes": list(ROUTES),
    }


@router.get("/api/cases")
def api_list_cases(request: Request) -> list[dict[str, object]]:
    return _orchestrator(request).list_cases()


@router.post("/api/cases/seed")
def seed_cases_api(
    request: Request, folder: str = "data/seed/cases", overwrite: bool = False
) -> dict[str, int]:
    orchestrator = _orchestrator(request)
    inserted, skipped = seed_cases(orchestrator.store, folder, overwrite=overwrite)
    return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}


@router.post("/api/cases")
def create_case(request: Request, payload: IntakePackage) -> dict[str, str]:
    orchestrator = _orchestrator(request)
    orchestrator.create_case(payload)
    return {"case_id": payload.case_id}


@router.get("/api/cases/{case_id}")
def get_case(request: Request, case_id: str) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    try:
        return orchestrator.store.get_case_state(case_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


@router.post("/api/cases/{case_id}/run")
def run_case(
    request: Request, case_id: str, requested_route: Route | None = None
) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    try:
        return orchestrator.run_case(case_id, requested_route=requested_route).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


@router.get("/api/approvals")
def api_list_approvals(request: Request) -> list[dict[str, object]]:
    approvals = _orchestrator(request).list_approvals()
    return [approval.model_dump() for approval in approvals]


@router.post("/api/approvals/{approval_id}/approve")
def approve_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayload,
) -> dict[str, str]:
    orchestrator = _orchestrator(request)
    try:
        orchestrator.apply_approval(
            approval_id,
            "approve",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    return {"status": "approved"}


@router.post("/api/approvals/{approval_id}/reject")
def reject_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayloadRequiredComment,
) -> dict[str, str]:
    orchestrator = _orchestrator(request)
    try:
        orchestrator.apply_approval(
            approval_id,
            "reject",
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    return {"status": "rejected"}


@router.post("/api/approvals/{approval_id}/override")
def override_case(
    request: Request,
    approval_id: str,
    payload: OverridePayload,
) -> dict[str, str]:
    orchestrator = _orchestrator(request)
    try:
        orchestrator.apply_approval(
            approval_id,
            "override_route",
            reviewer=payload.reviewer,
            comments=payload.comments,
            override_route=payload.route,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    return {"status": "overridden"}


@router.post("/api/approvals/{approval_id}/request-info")
def request_info_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayloadRequiredComment,
) -> dict[str, str]:
    orchestrator = _orchestrator(request)
    try:
        orchestrator.apply_approval(
            approval_id,
            "request_info",
            reviewer=payload.reviewer,
            request_info=payload.comments,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found") from exc
    return {"status": "requested_info"}


@router.get("/api/kpis")
def api_kpis(request: Request) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    return orchestrator.store.get_kpi_summary()


@router.get("/api/evals")
def api_get_evals(request: Request) -> list[dict[str, object]]:
    return [item.model_dump() for item in _orchestrator(request).store.get_eval_results()]


@router.post("/api/evals/run")
def run_evals(request: Request) -> dict[str, object]:
    from evals.runner import run_eval

    orchestrator = _orchestrator(request)
    result = run_eval(
        orchestrator.store, Path("data/held_out/cases"), Path("evals/baselines/latest.json")
    )
    return result


@router.get("/api/traces/{case_id}")
def get_traces_api(request: Request, case_id: str) -> list[dict[str, object]]:
    orchestrator = _orchestrator(request)
    if not orchestrator.store.get_status(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    traces = orchestrator.store.get_traces(case_id)
    return [trace.model_dump() for trace in traces]


def _dashboard_payload(request: Request) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    cases = orchestrator.list_cases()
    kpis = orchestrator.store.get_kpi_summary()
    evals = orchestrator.store.get_eval_results()
    eval_summary = orchestrator.store.get_eval_summary()
    return {
        "cases": cases,
        "kpi_summary": kpis,
        "eval_summary": eval_summary,
        "evals": [item.model_dump() for item in evals],
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    payload = _dashboard_payload(request)
    return _templates(request).TemplateResponse(
        "index.html",
        {
            "request": request,
            **payload,
            "routes": ROUTES,
        },
    )


@router.get("/cases", response_class=HTMLResponse)
def cases_page(
    request: Request, route: str | None = None, status: str | None = None
) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    cases = orchestrator.list_cases()
    filtered = [
        item
        for item in cases
        if (route is None or item.get("expected_route") == route)
        and (status is None or item.get("status") == status)
    ]
    return _templates(request).TemplateResponse(
        "cases.html",
        {
            "request": request,
            "cases": filtered,
            "route": route,
            "status": status,
            "ROUTES": ROUTES,
        },
    )


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_detail_page(request: Request, case_id: str) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    try:
        state = orchestrator.store.get_case_state(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc
    return _templates(request).TemplateResponse(
        "case_detail.html",
        {
            "request": request,
            "case": state,
            "approvals": orchestrator.store.list_approvals().copy(),
        },
    )


@router.post("/cases/{case_id}/run")
def case_run(request: Request, case_id: str) -> str:
    orchestrator = _orchestrator(request)
    orchestrator.run_case(case_id)
    return _redirect_response(f"/cases/{case_id}")


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request) -> HTMLResponse:
    approvals = _orchestrator(request).store.list_pending_approvals()
    return _templates(request).TemplateResponse(
        "approvals.html",
        {
            "request": request,
            "approvals": approvals,
            "ROUTES": ROUTES,
        },
    )


@router.get("/approvals/{approval_id}", response_class=HTMLResponse)
def approval_detail_page(
    request: Request,
    approval_id: str,
) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    approval = orchestrator.store.get_approval_by_id(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    case = orchestrator.store.get_case_state(approval.case_id)
    return _templates(request).TemplateResponse(
        "approval_detail.html",
        {
            "request": request,
            "approval": approval,
            "case": case,
            "ROUTES": ROUTES,
        },
    )


@router.post("/approvals/{approval_id}/approve")
def approval_action_approve(
    request: Request,
    approval_id: str,
    reviewer: str | None = Form(default=None),  # noqa: B008
    comments: str | None = Form(default=None),  # noqa: B008
) -> str:
    orchestrator = _orchestrator(request)
    orchestrator.apply_approval(
        approval_id,
        "approve",
        reviewer=reviewer,
        comments=comments,
    )
    return _redirect_response(f"/approvals/{approval_id}")


@router.post("/approvals/{approval_id}/reject")
def approval_action_reject(
    request: Request,
    approval_id: str,
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
) -> str:
    orchestrator = _orchestrator(request)
    orchestrator.apply_approval(
        approval_id,
        "reject",
        reviewer=reviewer,
        comments=comments,
    )
    return _redirect_response("/approvals")


@router.post("/approvals/{approval_id}/override")
def approval_action_override(
    request: Request,
    approval_id: str,
    route: Route = Form(...),  # noqa: B008
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
) -> str:
    orchestrator = _orchestrator(request)
    orchestrator.apply_approval(
        approval_id,
        "override_route",
        reviewer=reviewer,
        comments=comments,
        override_route=route,
    )
    return _redirect_response(f"/approvals/{approval_id}")


@router.post("/approvals/{approval_id}/request-info")
def approval_action_request_info(
    request: Request,
    approval_id: str,
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
) -> str:
    orchestrator = _orchestrator(request)
    orchestrator.apply_approval(
        approval_id,
        "request_info",
        reviewer=reviewer,
        request_info=comments,
    )
    return _redirect_response("/approvals")


@router.get("/evals", response_class=HTMLResponse)
def evals_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    eval_rows = orchestrator.store.get_eval_results()
    eval_summary = orchestrator.store.get_eval_summary()
    return _templates(request).TemplateResponse(
        "evals.html",
        {
            "request": request,
            "evals": [row.model_dump() for row in eval_rows],
            "eval_summary": eval_summary,
        },
    )


@router.post("/evals/run")
def run_evals_form(request: Request) -> str:
    from evals.runner import run_eval

    orchestrator = _orchestrator(request)
    run_eval(orchestrator.store, Path("data/held_out/cases"), Path("evals/baselines/latest.json"))
    return _redirect_response("/evals")


@router.get("/kpis", response_class=HTMLResponse)
def kpi_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    return _templates(request).TemplateResponse(
        "kpis.html",
        {
            "request": request,
            "kpi_summary": orchestrator.store.get_kpi_summary(),
        },
    )


@router.get("/playbook", response_class=HTMLResponse)
def playbook_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    return _templates(request).TemplateResponse(
        "playbook.html",
        {
            "request": request,
            "rules": orchestrator.playbook.rules,
        },
    )


def _redirect_response(target: str):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=target, status_code=303)
