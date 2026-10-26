from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import AuthError
from app.models import Comparison, Conversation
from app.services.comparisons import ComparisonInfo, ComparisonService, ComparisonStart

router = APIRouter(prefix="/api")


def service(request: Request) -> ComparisonService:
    return cast(ComparisonService, request.app.state.comparisons)


@router.post("/comparisons", response_model=ComparisonInfo, status_code=202)
async def start(body: ComparisonStart, request: Request) -> ComparisonInfo:
    return await service(request).start(request.state.owner_session.owner_id, body)


@router.get("/comparisons/{comparison_id}", response_model=ComparisonInfo)
def inspect(comparison_id: str, request: Request) -> ComparisonInfo:
    return service(request).get(request.state.owner_session.owner_id, comparison_id)


class ComparisonSummary(BaseModel):
    id: str
    created_at: int


@router.get("/conversations/{conversation_id}/comparisons", response_model=list[ComparisonSummary])
def history(conversation_id: str, request: Request) -> list[ComparisonSummary]:
    comparisons = service(request)
    owner = request.state.owner_session.owner_id
    with Session(comparisons.runs.engine) as db:
        conversation = db.get(Conversation, conversation_id)
        if not conversation or conversation.owner_id != owner:
            raise AuthError(404, "not_found", "Conversation not found.")
        groups = db.scalars(
            select(Comparison)
            .where(Comparison.conversation_id == conversation_id)
            .order_by(Comparison.created_at.desc(), Comparison.id)
            .limit(100)
        )
        return [ComparisonSummary(id=group.id, created_at=group.created_at) for group in groups]
