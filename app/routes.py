from __future__ import annotations

import hmac
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from schemas.case import IntakePackage, Route
from workflows.orchestrator import WorkflowOrchestrator
from workflows.routing import ROUTES
from workflows.seeding import seed_cases

router = APIRouter()
SAFE_SEED_FOLDERS = {
    "seed": Path("data/seed/cases"),
    "held_out": Path("data/held_out/cases"),
}


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


def _settings(request: Request):
    return request.app.state.settings


def _configured_admin_token(request: Request) -> str | None:
    token = _settings(request).admin_token
    return token if token else None


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix) :]
    return None


def _is_admin_token_valid(request: Request, token: str | None) -> bool:
    expected = _configured_admin_token(request)
    return bool(expected and token and hmac.compare_digest(token, expected))


def _admin_token_from_request(
    request: Request,
    x_admin_token: str | None = None,
    authorization: str | None = None,
) -> str | None:
    header_token = request.headers.get("x-admin-token")
    header_authorization = request.headers.get("authorization")
    return (
        x_admin_token
        or header_token
        or _extract_bearer_token(authorization)
        or _extract_bearer_token(header_authorization)
        or request.query_params.get("admin_token")
    )


def _require_api_admin(
    request: Request,
    x_admin_token: str | None = None,
    authorization: str | None = None,
) -> None:
    if not _configured_admin_token(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin actions are disabled until ADMIN_TOKEN is configured.",
        )
    if not _is_admin_token_valid(
        request, _admin_token_from_request(request, x_admin_token, authorization)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required.")


def _csrf_action(method: str, path: str) -> str:
    return f"{method.upper()}:{path}"


def _csrf_token(request: Request, action: str) -> str:
    secret = _configured_admin_token(request)
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), action.encode("utf-8"), "sha256").hexdigest()


def _verify_csrf(request: Request, action: str, token: str | None) -> bool:
    expected = _csrf_token(request, action)
    return bool(expected and token and hmac.compare_digest(token, expected))


def _require_form_admin(
    request: Request,
    admin_token: str | None,
    csrf_token: str | None,
) -> None:
    if not _configured_admin_token(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin actions are disabled until ADMIN_TOKEN is configured.",
        )
    if not _is_admin_token_valid(request, admin_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required.")
    action = _csrf_action(request.method, request.url.path)
    if not _verify_csrf(request, action, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required.")


def _is_admin_request(request: Request) -> bool:
    return _is_admin_token_valid(request, _admin_token_from_request(request))


def _template_security_context(request: Request) -> dict[str, object]:
    admin_token = request.query_params.get("admin_token")
    admin_mode = _is_admin_token_valid(request, admin_token)

    def csrf_token_for(method: str, path: str) -> str:
        return _csrf_token(request, _csrf_action(method, path))

    return {
        "admin_enabled": bool(_configured_admin_token(request)),
        "admin_mode": admin_mode,
        "admin_token": admin_token if admin_mode else "",
        "csrf_token_for": csrf_token_for,
    }


def _public_case_summary(state) -> dict[str, object]:
    routing = state.routing_decision.model_dump(mode="json") if state.routing_decision else None
    approval = None
    if state.approval is not None:
        approval = {
            "approval_id": state.approval.approval_id,
            "case_id": state.approval.case_id,
            "status": state.approval.status,
            "original_route": state.approval.original_route,
            "final_route": state.approval.final_route,
            "created_at": state.approval.created_at.isoformat(),
            "resolved_at": state.approval.resolved_at.isoformat()
            if state.approval.resolved_at
            else None,
        }
    return {
        "case_id": state.case_id,
        "state": state.state,
        "customer_name": state.intake.customer_name,
        "account_name": state.intake.account_name,
        "scenario_summary": state.intake.scenario_summary,
        "expected_route": state.intake.expected_route,
        "expected_approval_required": state.intake.expected_approval_required,
        "normalized_case": {
            "case_id": state.normalized_case.case_id,
            "customer_name": state.normalized_case.customer_name,
            "package_complete": state.normalized_case.package_complete,
            "missing_info_count": len(state.normalized_case.missing_info),
            "risk_signals": state.normalized_case.risk_signals,
        },
        "findings": [
            {
                "finding_id": finding.finding_id,
                "rule_id": finding.rule_id,
                "finding_type": finding.finding_type,
                "severity": finding.severity,
                "route": finding.route,
                "summary": finding.summary,
                "confidence": finding.confidence,
                "source_agent": finding.source_agent,
                "evidence_count": len(finding.evidence),
                "evidence_sources": sorted(
                    {span.source_document_type for span in finding.evidence}
                ),
            }
            for finding in state.findings
        ],
        "routing_decision": routing,
        "approval": approval,
        "brief": state.brief.model_dump(mode="json") if state.brief else None,
        "tasks": [task.model_dump(mode="json") for task in state.tasks],
        "trace_count": len(state.traces),
    }


def _run_admin_action(action: Callable[[], object]) -> object:
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
    dataset: str = "seed",
    overwrite: bool = False,
) -> dict[str, int]:
    _require_api_admin(request, x_admin_token, authorization)
    folder = SAFE_SEED_FOLDERS.get(dataset)
    if folder is None:
        allowed = ", ".join(sorted(SAFE_SEED_FOLDERS))
        raise HTTPException(status_code=400, detail=f"Unsupported seed dataset. Use: {allowed}.")
    orchestrator = _orchestrator(request)
    inserted, skipped = seed_cases(orchestrator.store, folder, overwrite=overwrite)
    return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}


@router.post("/api/cases")
def create_case(
    request: Request,
    payload: IntakePackage,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_api_admin(request, x_admin_token, authorization)
    orchestrator = _orchestrator(request)
    orchestrator.create_case(payload)
    return {"case_id": payload.case_id}


@router.get("/api/cases/{case_id}")
def get_case(request: Request, case_id: str) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    try:
        state = orchestrator.store.get_case_state(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc
    if _is_admin_request(request):
        return state.model_dump(mode="json")
    return _public_case_summary(state)


@router.post("/api/cases/{case_id}/run")
def run_case(
    request: Request,
    case_id: str,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require_api_admin(request, x_admin_token, authorization)
    orchestrator = _orchestrator(request)
    try:
        return orchestrator.run_case(case_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/approvals")
def api_list_approvals(request: Request) -> list[dict[str, object]]:
    approvals = _orchestrator(request).list_approvals()
    return [approval.model_dump() for approval in approvals]


@router.post("/api/approvals/{approval_id}/approve")
def approve_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayload,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_api_admin(request, x_admin_token, authorization)
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "approved"}


@router.post("/api/approvals/{approval_id}/reject")
def reject_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayloadRequiredComment,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_api_admin(request, x_admin_token, authorization)
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "rejected"}


@router.post("/api/approvals/{approval_id}/override")
def override_case(
    request: Request,
    approval_id: str,
    payload: OverridePayload,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_api_admin(request, x_admin_token, authorization)
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "overridden"}


@router.post("/api/approvals/{approval_id}/request-info")
def request_info_case(
    request: Request,
    approval_id: str,
    payload: ApprovalPayloadRequiredComment,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    _require_api_admin(request, x_admin_token, authorization)
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "requested_info"}


@router.get("/api/kpis")
def api_kpis(request: Request) -> dict[str, object]:
    orchestrator = _orchestrator(request)
    return orchestrator.store.get_kpi_summary()


@router.get("/api/evals")
def api_get_evals(request: Request) -> list[dict[str, object]]:
    return [item.model_dump() for item in _orchestrator(request).store.get_eval_results()]


@router.post("/api/evals/run")
def run_evals(
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    from evals.runner import RUNTIME_EVAL_OUTPUT, run_eval

    _require_api_admin(request, x_admin_token, authorization)
    orchestrator = _orchestrator(request)
    result = run_eval(
        orchestrator.store, Path("data/held_out/cases"), RUNTIME_EVAL_OUTPUT
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
        request,
        "index.html",
        {
            "request": request,
            **payload,
            "routes": ROUTES,
            **_template_security_context(request),
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
        if (route is None or item.get("actual_route") == route)
        and (status is None or item.get("status") == status)
    ]
    return _templates(request).TemplateResponse(
        request,
        "cases.html",
        {
            "request": request,
            "cases": filtered,
            "route": route,
            "status": status,
            "ROUTES": ROUTES,
            **_template_security_context(request),
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
        request,
        "case_detail.html",
        {
            "request": request,
            "case": state,
            "approvals": orchestrator.store.list_approvals().copy(),
            **_template_security_context(request),
        },
    )


@router.post("/cases/{case_id}/run")
def case_run(request: Request, case_id: str) -> str:
    raise HTTPException(status_code=405, detail="Admin form token required.")


@router.post("/cases/{case_id}/run/admin")
def case_run_admin(
    request: Request,
    case_id: str,
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    _run_admin_action(lambda: orchestrator.run_case(case_id))
    return _redirect_response(f"/cases/{case_id}?admin_token={admin_token}")


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request) -> HTMLResponse:
    approvals = _orchestrator(request).store.list_pending_approvals()
    return _templates(request).TemplateResponse(
        request,
        "approvals.html",
        {
            "request": request,
            "approvals": approvals,
            "ROUTES": ROUTES,
            **_template_security_context(request),
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
        request,
        "approval_detail.html",
        {
            "request": request,
            "approval": approval,
            "case": case,
            "ROUTES": ROUTES,
            **_template_security_context(request),
        },
    )


@router.post("/approvals/{approval_id}/approve")
def approval_action_approve(
    request: Request,
    approval_id: str,
    reviewer: str | None = Form(default=None),  # noqa: B008
    comments: str | None = Form(default=None),  # noqa: B008
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    _run_admin_action(
        lambda: orchestrator.apply_approval(
            approval_id,
            "approve",
            reviewer=reviewer,
            comments=comments,
        )
    )
    return _redirect_response(f"/approvals/{approval_id}?admin_token={admin_token}")


@router.post("/approvals/{approval_id}/reject")
def approval_action_reject(
    request: Request,
    approval_id: str,
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    _run_admin_action(
        lambda: orchestrator.apply_approval(
            approval_id,
            "reject",
            reviewer=reviewer,
            comments=comments,
        )
    )
    return _redirect_response(f"/approvals?admin_token={admin_token}")


@router.post("/approvals/{approval_id}/override")
def approval_action_override(
    request: Request,
    approval_id: str,
    route: Route = Form(...),  # noqa: B008
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    _run_admin_action(
        lambda: orchestrator.apply_approval(
            approval_id,
            "override_route",
            reviewer=reviewer,
            comments=comments,
            override_route=route,
        )
    )
    return _redirect_response(f"/approvals/{approval_id}?admin_token={admin_token}")


@router.post("/approvals/{approval_id}/request-info")
def approval_action_request_info(
    request: Request,
    approval_id: str,
    reviewer: str = Form(...),  # noqa: B008
    comments: str = Form(...),  # noqa: B008
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    _run_admin_action(
        lambda: orchestrator.apply_approval(
            approval_id,
            "request_info",
            reviewer=reviewer,
            request_info=comments,
        )
    )
    return _redirect_response(f"/approvals?admin_token={admin_token}")


@router.get("/evals", response_class=HTMLResponse)
def evals_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    eval_rows = orchestrator.store.get_eval_results()
    eval_summary = orchestrator.store.get_eval_summary()
    return _templates(request).TemplateResponse(
        request,
        "evals.html",
        {
            "request": request,
            "evals": [row.model_dump() for row in eval_rows],
            "eval_summary": eval_summary,
            **_template_security_context(request),
        },
    )


@router.post("/evals/run")
def run_evals_form(
    request: Request,
    admin_token: str = Form(...),  # noqa: B008
    csrf_token: str = Form(...),  # noqa: B008
) -> str:
    from evals.runner import RUNTIME_EVAL_OUTPUT, run_eval

    _require_form_admin(request, admin_token, csrf_token)
    orchestrator = _orchestrator(request)
    run_eval(orchestrator.store, Path("data/held_out/cases"), RUNTIME_EVAL_OUTPUT)
    return _redirect_response(f"/evals?admin_token={admin_token}")


@router.get("/kpis", response_class=HTMLResponse)
def kpi_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    return _templates(request).TemplateResponse(
        request,
        "kpis.html",
        {
            "request": request,
            "kpi_summary": orchestrator.store.get_kpi_summary(),
            **_template_security_context(request),
        },
    )


@router.get("/playbook", response_class=HTMLResponse)
def playbook_page(request: Request) -> HTMLResponse:
    orchestrator = _orchestrator(request)
    return _templates(request).TemplateResponse(
        request,
        "playbook.html",
        {
            "request": request,
            "rules": orchestrator.playbook.rules,
            **_template_security_context(request),
        },
    )


def _redirect_response(target: str):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=target, status_code=303)
