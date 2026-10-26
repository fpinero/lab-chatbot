import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.service import AuthError, AuthService
from app.models import Charge, Conversation, Preferences, Run, RunAttachment
from app.services.catalog import CatalogInfo, CatalogService
from app.services.runs import TERMINAL, RunInfo, RunService, RunStart

router = APIRouter(prefix="/api")


class ConversationInput(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=160)


class ConversationInfo(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int


class ConversationDetail(ConversationInfo):
    runs: list[RunInfo]


class FavoriteInput(BaseModel):
    favorites: list[str] = Field(max_length=50)


def owner(request: Request) -> str:
    return str(request.state.owner_session.owner_id)


def runs(request: Request) -> RunService:
    return cast(RunService, request.app.state.runs)


def conversation(db: Session, owner_id: str, conversation_id: str) -> Conversation:
    item = db.get(Conversation, conversation_id)
    if not item or item.owner_id != owner_id:
        raise AuthError(404, "not_found", "Conversation not found.")
    return item


def info(item: Conversation) -> ConversationInfo:
    return ConversationInfo(
        id=item.id, title=item.title, created_at=item.created_at, updated_at=item.updated_at
    )


@router.get("/models", response_model=CatalogInfo)
async def models(request: Request) -> CatalogInfo:
    catalog: CatalogService = request.app.state.catalog
    return await catalog.get()


@router.post("/models/refresh", response_model=CatalogInfo)
async def refresh_models(request: Request) -> CatalogInfo:
    catalog: CatalogService = request.app.state.catalog
    return await catalog.get(refresh=True)


@router.get("/preferences", response_model=FavoriteInput)
def get_preferences(request: Request) -> FavoriteInput:
    with Session(runs(request).engine) as db:
        preferences = db.get(Preferences, owner(request))
        return FavoriteInput(
            favorites=json.loads(preferences.favorites_json) if preferences else []
        )


@router.patch("/preferences", response_model=FavoriteInput)
def set_preferences(body: FavoriteInput, request: Request) -> FavoriteInput:
    if any(len(value) > 200 for value in body.favorites):
        raise AuthError(422, "invalid_model", "Invalid favorite model identifier.")
    with Session(runs(request).engine) as db:
        item = db.get(Preferences, owner(request))
        if not item:
            item = Preferences(owner_id=owner(request))
            db.add(item)
        item.favorites_json = json.dumps(list(dict.fromkeys(body.favorites)))
        db.commit()
    return body


@router.get("/conversations", response_model=list[ConversationInfo])
def list_conversations(
    request: Request,
    q: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0, le=100000),
) -> list[ConversationInfo]:
    with Session(runs(request).engine) as db:
        query = select(Conversation).where(Conversation.owner_id == owner(request))
        if q:
            pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Conversation.title.ilike(f"%{pattern}%", escape="\\"))
        return [
            info(item)
            for item in db.scalars(
                query.order_by(Conversation.updated_at.desc(), Conversation.id)
                .offset(offset)
                .limit(100)
            )
        ]


@router.post("/conversations", response_model=ConversationInfo, status_code=201)
def create_conversation(body: ConversationInput, request: Request) -> ConversationInfo:
    service = runs(request)
    with Session(service.engine) as db:
        item = Conversation(
            id=uuid4().hex,
            owner_id=owner(request),
            title=body.title,
            created_at=service.now(),
            updated_at=service.now(),
        )
        db.add(item)
        db.commit()
        return info(item)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, request: Request) -> ConversationDetail:
    service = runs(request)
    with Session(service.engine) as db:
        item = conversation(db, owner(request), conversation_id)
        history = db.scalars(select(Run).where(Run.conversation_id == item.id).order_by(Run.turn))
        return ConversationDetail(
            **info(item).model_dump(), runs=[service.info(db, run) for run in history]
        )


@router.patch("/conversations/{conversation_id}", response_model=ConversationInfo)
def rename_conversation(
    conversation_id: str, body: ConversationInput, request: Request
) -> ConversationInfo:
    with Session(runs(request).engine) as db:
        item = conversation(db, owner(request), conversation_id)
        item.title = body.title
        db.commit()
        return info(item)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, request: Request, confirm: bool = False) -> Response:
    if not confirm:
        raise AuthError(409, "confirmation_required", "Confirm conversation deletion explicitly.")
    with Session(runs(request).engine) as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        item = conversation(db, owner(request), conversation_id)
        active = db.scalar(
            select(Run.id)
            .where(Run.conversation_id == item.id, Run.status.not_in(TERMINAL))
            .limit(1)
        )
        if active:
            raise AuthError(
                409, "conversation_busy", "Stop active runs before deleting this conversation."
            )
        attachment_ids = list(
            db.scalars(
                select(RunAttachment.attachment_id)
                .join(Run, Run.id == RunAttachment.run_id)
                .where(Run.conversation_id == item.id)
            )
        )
        db.execute(delete(Conversation).where(Conversation.id == item.id))
        db.commit()
    runs(request).attachments.collect(attachment_ids)
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: str, request: Request, format: Literal["json", "markdown"] = "markdown"
) -> Response:
    detail = get_conversation(conversation_id, request)
    if format == "json":
        return Response(
            detail.model_dump_json(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{detail.id}.json"'},
        )
    lines = [f"# {detail.title}"]
    for run in detail.runs:
        lines += [
            "",
            "## User",
            "",
            run.prompt,
            "",
            f"## {run.model_name}",
            "",
            run.output,
            "",
            f"Status: {run.status}. Accounting: {run.accounting_state}.",
        ]
    return Response(
        "\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{detail.id}.md"'},
    )


@router.post("/runs/{run_id}/fork", response_model=ConversationDetail, status_code=201)
def fork_run(run_id: str, request: Request) -> ConversationDetail:
    identifier = runs(request).fork(owner(request), run_id)
    return get_conversation(identifier, request)


@router.post("/runs", response_model=RunInfo, status_code=202)
async def start_run(body: RunStart, request: Request) -> RunInfo:
    return await runs(request).start(owner(request), body)


@router.get("/runs/{run_id}", response_model=RunInfo)
def get_run(run_id: str, request: Request) -> RunInfo:
    return runs(request).get(owner(request), run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunInfo)
async def cancel_run(run_id: str, request: Request) -> RunInfo:
    return await runs(request).cancel_task(owner(request), run_id)


@router.post("/runs/{run_id}/reconcile", response_model=RunInfo)
async def reconcile_run(run_id: str, request: Request) -> RunInfo:
    return await runs(request).reconcile(owner(request), run_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    service = runs(request)
    auth: AuthService = request.app.state.auth
    initial = service.get(owner(request), run_id)

    async def events() -> AsyncIterator[str]:
        current, previous, last_seq = initial, "", -1
        last_auth, last_heartbeat = 0.0, time.monotonic()
        while not await request.is_disconnected():
            if time.monotonic() - last_auth >= 1:
                try:
                    await run_in_threadpool(auth.authenticate, request, touch=False)
                except AuthError:
                    yield 'event: session.expired\ndata: {"code":"session_required"}\n\n'
                    return
                last_auth = time.monotonic()
            current = await run_in_threadpool(service.get, owner(request), run_id)
            if current.sequence != last_seq:
                kind = "run.snapshot" if last_seq == -1 else "text.delta"
                if last_seq != -1 and current.status in TERMINAL:
                    kind = {"succeeded": "run.completed", "cancelled": "run.cancelled"}.get(
                        current.status, "run.failed"
                    )
                elif last_seq != -1 and not previous and not current.output:
                    kind = "run.started"
                delta = (
                    current.output[len(previous) :] if current.output.startswith(previous) else ""
                )
                payload = {
                    "run_id": run_id,
                    "sequence": current.sequence,
                    "text": delta,
                    "run": current.model_dump(),
                }
                event_sequence = current.sequence * 2 + int(
                    last_seq == -1 and current.status in TERMINAL
                )
                if last_seq != -1 and current.status in TERMINAL and current.usage:
                    payload["sequence"] = event_sequence
                    yield (
                        f"id: {event_sequence}\nevent: usage.updated\n"
                        f"data: {json.dumps(payload)}\n\n"
                    )
                    event_sequence += 1
                payload["sequence"] = event_sequence
                yield f"id: {event_sequence}\nevent: {kind}\ndata: {json.dumps(payload)}\n\n"
                previous, last_seq = current.output, current.sequence
            if current.status in TERMINAL:
                return
            if time.monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


class UsageInfo(BaseModel):
    currency: Literal["USD"] = "USD"
    daily_actual_microusd: int
    outstanding_microusd: int
    uncertain_count: int
    request_limit_microusd: int
    daily_limit_microusd: int
    simulated: bool
    conversations: dict[str, int]


@router.get("/usage", response_model=UsageInfo)
def usage(request: Request) -> UsageInfo:
    from app.services.runs import allowance_microusd

    service = runs(request)
    day = service.now() // 86400 * 86400
    actual, reserved, uncertain = 0, 0, 0
    totals: dict[str, int] = {}
    with Session(service.engine) as db:
        for charge in db.scalars(select(Charge).where(Charge.owner_id == owner(request))):
            if charge.state != "settled":
                reserved += charge.reserved_microusd
                uncertain += int(charge.state == "uncertain")
            if charge.created_at >= day and charge.actual_microusd is not None:
                actual += charge.actual_microusd
            run = db.get(Run, charge.run_id) if charge.run_id else None
            if run:
                totals[run.conversation_id] = totals.get(run.conversation_id, 0) + (
                    charge.actual_microusd or 0
                )
    return UsageInfo(
        daily_actual_microusd=actual,
        outstanding_microusd=reserved,
        uncertain_count=uncertain,
        request_limit_microusd=allowance_microusd(service.settings.max_request_usd),
        daily_limit_microusd=allowance_microusd(service.settings.daily_budget_usd),
        simulated=service.settings.provider_mode == "mock",
        conversations=totals,
    )
