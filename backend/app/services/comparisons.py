import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import AuthError, digest
from app.models import Charge, Comparison, Conversation, Run
from app.services.runs import TERMINAL, RunInfo, RunService, RunStart


class ComparisonStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(max_length=64)
    model_ids: list[str] = Field(min_length=2, max_length=4)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    prompt: str = Field(default="", max_length=24000)
    system_prompt: str = Field(default="", max_length=12000)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    retry_of: str | None = Field(default=None, max_length=64)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    verification_run: bool = False
    request_allowance_microusd: int | None = Field(default=None, ge=0, le=100000000)

    @model_validator(mode="after")
    def validate_candidates(self) -> "ComparisonStart":
        if len(set(self.model_ids)) != len(self.model_ids) or any(
            not value or len(value) > 200 for value in self.model_ids
        ):
            raise ValueError("Choose two to four distinct model identifiers.")
        if not self.retry_of and not self.prompt.strip():
            raise ValueError("A prompt or saved input is required.")
        return self

    def candidate(self, model_id: str, key: str) -> RunStart:
        return RunStart(
            **self.model_dump(exclude={"model_ids", "idempotency_key"}),
            model_id=model_id,
            idempotency_key=key,
        )


class ComparisonInfo(BaseModel):
    id: str
    conversation_id: str
    status: str
    snapshot_hash: str
    created_at: int
    candidates: list[RunInfo]
    previous_runs_count: int


class ComparisonService:
    def __init__(self, runs: RunService) -> None:
        self.runs = runs

    def info(self, db: Session, group: Comparison) -> ComparisonInfo:
        records = list(
            db.scalars(select(Run).where(Run.comparison_id == group.id).order_by(Run.turn))
        )
        latest: dict[str, Run] = {}
        for run in records:
            latest[run.model_id] = run
        candidates = [self.runs.info(db, run) for run in latest.values()]
        status = (
            "running"
            if any(run.status not in TERMINAL for run in candidates)
            else "succeeded"
            if all(run.status == "succeeded" for run in candidates)
            else "partial_failure"
            if any(run.status == "succeeded" for run in candidates)
            else "failed"
        )
        return ComparisonInfo(
            id=group.id,
            conversation_id=group.conversation_id,
            status=status,
            snapshot_hash=digest(group.snapshot_json),
            created_at=group.created_at,
            candidates=candidates,
            previous_runs_count=len(records) - len(candidates),
        )

    def get(self, owner: str, group_id: str) -> ComparisonInfo:
        with Session(self.runs.engine) as db:
            group = db.get(Comparison, group_id)
            if not group or group.owner_id != owner:
                raise AuthError(404, "not_found", "Comparison not found.")
            return self.info(db, group)

    def existing(
        self, db: Session, owner: str, body: ComparisonStart, fingerprint: str
    ) -> ComparisonInfo | None:
        group = db.scalar(
            select(Comparison).where(
                Comparison.owner_id == owner, Comparison.idempotency_key == body.idempotency_key
            )
        )
        if group:
            if group.request_hash != fingerprint:
                raise AuthError(
                    409, "idempotency_conflict", "This comparison key belongs to another input."
                )
            return self.info(db, group)
        first_key = digest(f"comparison:{body.idempotency_key}:0")
        if db.scalar(
            select(Charge.id).where(Charge.owner_id == owner, Charge.idempotency_key == first_key)
        ):
            raise AuthError(
                410,
                "comparison_deleted",
                "The original comparison was deleted. Submit deliberately with a new key.",
            )
        return None

    async def start(self, owner: str, body: ComparisonStart) -> ComparisonInfo:
        fingerprint = digest(json.dumps(body.model_dump(), sort_keys=True))
        with Session(self.runs.engine) as db:
            existing = self.existing(db, owner, body, fingerprint)
            if existing:
                return existing
        await self.runs.authorize_dispatch()
        catalog = {model.id: model for model in (await self.runs.catalog.get()).models}
        if any(identifier not in catalog for identifier in body.model_ids):
            raise AuthError(
                422, "invalid_model", "Choose every candidate from the current model catalog."
            )
        models = [catalog[identifier] for identifier in body.model_ids]
        requests = [
            body.candidate(model.id, digest(f"comparison:{body.idempotency_key}:{index}"))
            for index, model in enumerate(models)
        ]
        for model, request in zip(models, requests, strict=True):
            self.runs.validate_model(model, request)
        with Session(self.runs.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            existing = self.existing(db, owner, body, fingerprint)
            if existing:
                return existing
            conversation = db.get(Conversation, body.conversation_id)
            if not conversation or conversation.owner_id != owner:
                raise AuthError(404, "not_found", "Conversation not found.")
            messages, prompt, turn_ids = self.runs.snapshot(db, owner, requests[0], conversation)
            estimates = [self.runs.estimate(model, messages, body.max_tokens) for model in models]
            total = sum(estimates)
            if (
                body.request_allowance_microusd is not None
                and total > body.request_allowance_microusd
            ):
                raise AuthError(
                    402,
                    "request_allowance",
                    "The combined estimate exceeds this request allowance.",
                )
            self.runs.check_budget(
                db,
                owner,
                total,
                all(model.simulated for model in models),
                body.verification_run,
                len(models),
            )
            group = Comparison(
                id=uuid4().hex,
                owner_id=owner,
                conversation_id=conversation.id,
                idempotency_key=body.idempotency_key,
                request_hash=fingerprint,
                snapshot_json=json.dumps(messages),
                created_at=self.runs.now(),
            )
            db.add(group)
            db.flush()
            candidates = [
                self.runs.create_queued(
                    db, owner, request, model, messages, prompt, turn_ids, estimate, group.id
                )
                for model, request, estimate in zip(models, requests, estimates, strict=True)
            ]
            conversation.updated_at = self.runs.now()
            db.commit()
            result = self.info(db, group)
            identifiers = [run.id for run in candidates]
        for identifier in identifiers:
            self.runs.schedule(identifier)
        return result
