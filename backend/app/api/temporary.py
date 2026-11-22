"""Authenticated, session-bound temporary chat endpoints."""

from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.chat import ConversationInfo, stream_events
from app.auth.service import AuthError
from app.services.attachments import AttachmentInfo
from app.services.runs import RunInfo, RunStart
from app.services.temporary import TemporaryChats, TemporaryWorker

router = APIRouter(prefix="/api/temporary-chats")


def manager(request: Request) -> TemporaryChats:
    return cast(TemporaryChats, request.app.state.temporary)


def worker(identifier: str, request: Request) -> TemporaryWorker:
    return manager(request).get(identifier, request.state.owner_session)


class MemoryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=1000)
    mime: str = Field(max_length=200)
    data: str = Field(max_length=14 * 1024 * 1024)


class MemoryUpload(BaseModel):
    files: list[MemoryFile] = Field(min_length=1, max_length=5)


@router.post("", response_model=ConversationInfo, status_code=201)
async def create(request: Request) -> ConversationInfo:
    chat = manager(request).create(request.state.owner_session)
    return ConversationInfo(
        id=chat.identifier, title="Temporary chat", created_at=chat.touched, updated_at=chat.touched
    )


@router.post("/{identifier}/touch", status_code=204)
def touch(identifier: str, request: Request) -> Response:
    worker(identifier, request)
    return Response(status_code=204)


@router.delete("/{identifier}", status_code=204)
async def close(identifier: str, request: Request) -> Response:
    try:
        chat = worker(identifier, request)
    except AuthError as exc:
        if exc.status == 410:
            return Response(status_code=204)
        raise
    await manager(request).close(chat)
    return Response(status_code=204)


@router.post("/{identifier}/attachments", response_model=list[AttachmentInfo], status_code=201)
async def upload(identifier: str, body: MemoryUpload, request: Request) -> list[AttachmentInfo]:
    chat = worker(identifier, request)
    assets = chat.assets
    main = manager(request).main
    if assets.upload_slots.locked():
        raise AuthError(429, "upload_busy", "The upload processor is busy. Try again shortly.")
    main.attachments.reserve_upload(chat.owner)
    async with chat.operation, assets.upload_slots:
        return await assets.upload_memory([file.model_dump() for file in body.files])


@router.post("/{identifier}/runs", response_model=RunInfo, status_code=201)
async def start(identifier: str, body: RunStart, request: Request) -> RunInfo:
    chat = worker(identifier, request)
    async with chat.operation:
        return await chat.runs.start(chat.owner, body)


@router.get("/{identifier}/runs/{run_id}", response_model=RunInfo)
def get_run(identifier: str, run_id: str, request: Request) -> RunInfo:
    chat = worker(identifier, request)
    return chat.runs.get(chat.owner, run_id)


@router.post("/{identifier}/runs/{run_id}/cancel", response_model=RunInfo)
async def cancel(identifier: str, run_id: str, request: Request) -> RunInfo:
    chat = worker(identifier, request)
    return await chat.runs.cancel_task(chat.owner, run_id)


@router.post("/{identifier}/runs/{run_id}/reconcile", response_model=RunInfo)
async def reconcile(identifier: str, run_id: str, request: Request) -> RunInfo:
    chat = worker(identifier, request)
    return await chat.runs.reconcile(chat.owner, run_id)


@router.get("/{identifier}/runs/{run_id}/events")
async def events(identifier: str, run_id: str, request: Request) -> StreamingResponse:
    chat = worker(identifier, request)
    return await stream_events(run_id, request, chat.runs)
