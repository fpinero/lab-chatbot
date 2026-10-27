import asyncio
import json
import time
from collections.abc import Callable
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Engine, case, func, or_, select
from sqlalchemy.orm import Session

from app.auth.service import AuthError, digest
from app.config import Settings
from app.models import AuthBucket, Charge, Conversation, MediaJob, Run, RunAttachment
from app.providers.chat import ChatProvider, ProviderError
from app.services.attachments import AttachmentInfo, AttachmentService
from app.services.catalog import CatalogService, ModelInfo

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


def microusd(value: Decimal) -> int:
    if not value.is_finite() or value < 0:
        raise ValueError("Invalid USD amount.")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def sanitized_usage(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if raw.get("cost") is not None:
        try:
            value = Decimal(str(raw["cost"]))
            if value.is_finite() and value >= 0:
                result["cost"] = str(value)
        except (ValueError, ArithmeticError):
            pass
    for key in ["prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"]:
        if (
            isinstance(raw.get(key), int)
            and not isinstance(raw[key], bool)
            and 0 <= raw[key] <= 1_000_000_000
        ):
            result[key] = raw[key]
    for key, token_key in [
        ("prompt_tokens_details", "cached_tokens"),
        ("completion_tokens_details", "reasoning_tokens"),
    ]:
        details = raw.get(key)
        if (
            isinstance(details, dict)
            and isinstance(details.get(token_key), int)
            and 0 <= details[token_key] <= 1_000_000_000
        ):
            result[key] = {token_key: details[token_key]}
    return result


def allowance_microusd(value: Decimal) -> int:
    if not value.is_finite() or value < 0:
        raise ValueError("Invalid USD allowance.")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))


class RunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(max_length=64)
    model_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    prompt: str = Field(default="", max_length=24000)
    system_prompt: str = Field(default="", max_length=12000)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    verification_run: bool = False
    retry_of: str | None = Field(default=None, max_length=64)
    request_allowance_microusd: int | None = Field(default=None, ge=0, le=100000000)

    @model_validator(mode="after")
    def require_prompt(self) -> "RunStart":
        if not self.retry_of and not self.prompt.strip():
            raise ValueError("A prompt is required.")
        return self


class RunInfo(BaseModel):
    id: str
    conversation_id: str
    model_id: str
    model_name: str
    turn: int
    prompt: str
    output: str
    status: str
    error_code: str | None
    provider: str | None
    generation_id: str | None
    sequence: int
    created_at: int
    started_at: int | None
    completed_at: int | None
    first_token_ms: int | None
    elapsed_ms: int | None
    reserved_microusd: int
    actual_microusd: int | None
    queue_delay_ms: int | None
    comparison_id: str | None
    attachments: list[AttachmentInfo]
    accounting_state: str
    usage: dict[str, Any] | None
    simulated: bool
    settings: dict[str, Any]


class RunService:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        provider: ChatProvider,
        catalog: CatalogService,
        now: Callable[[], int],
        attachments: AttachmentService,
    ) -> None:
        self.engine, self.settings, self.provider, self.catalog, self.now = (
            engine,
            settings,
            provider,
            catalog,
            now,
        )
        self.attachments = attachments
        self.slots = asyncio.Semaphore(2)
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.closing = False

    def info(self, db: Session, run: Run) -> RunInfo:
        charge = db.scalar(select(Charge).where(Charge.run_id == run.id))
        settings = json.loads(run.settings_json)
        inherited = settings.get("imported_from") is not None
        if not charge and not inherited:
            raise AuthError(500, "accounting_unavailable", "Usage accounting is unavailable.")
        return RunInfo(
            id=run.id,
            conversation_id=run.conversation_id,
            model_id=run.model_id,
            model_name=settings["model_name"],
            turn=run.turn,
            prompt=run.prompt,
            output=run.output,
            status=run.status,
            error_code=run.error_code,
            provider=run.provider,
            generation_id=run.generation_id,
            sequence=run.sequence,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            first_token_ms=run.first_token_ms,
            elapsed_ms=run.elapsed_ms,
            reserved_microusd=charge.reserved_microusd if charge else 0,
            actual_microusd=charge.actual_microusd
            if charge
            else settings.get("original_actual_microusd"),
            accounting_state=charge.state if charge else "inherited",
            comparison_id=run.comparison_id,
            queue_delay_ms=settings.get("queue_delay_ms"),
            attachments=[
                AttachmentInfo.model_validate(item) for item in settings.get("attachments", [])
            ],
            usage=json.loads(run.usage_json) if run.usage_json else None,
            simulated=settings["simulated"],
            settings=settings,
        )

    def get(self, owner: str, run_id: str) -> RunInfo:
        with Session(self.engine) as db:
            run = db.get(Run, run_id)
            if not run or run.owner_id != owner:
                raise AuthError(404, "not_found", "Run not found.")
            return self.info(db, run)

    def existing(self, db: Session, owner: str, key: str, request_hash: str) -> RunInfo | None:
        charge = db.scalar(
            select(Charge).where(Charge.owner_id == owner, Charge.idempotency_key == key)
        )
        if not charge:
            return None
        if charge.request_hash != request_hash:
            raise AuthError(
                409,
                "idempotency_conflict",
                "This submission key already belongs to another request.",
            )
        run = db.get(Run, charge.run_id) if charge.run_id else None
        if not run:
            raise AuthError(
                410,
                "run_deleted",
                "The original run was deleted. Submit deliberately with a new key.",
            )
        return self.info(db, run)

    def estimate(self, model: ModelInfo, messages: list[dict[str, Any]], maximum: int) -> int:
        # UTF-8 bytes plus framing provide a deliberately conservative token approximation.
        input_upper = (
            sum(len(json.dumps(message, ensure_ascii=False).encode()) + 64 for message in messages)
            + 256
        )
        image_references = [
            reference
            for message in messages
            for reference in message.get("_attachments", [])
            if reference["kind"] == "image"
        ]
        if image_references and "image" not in model.input_modalities:
            raise AuthError(
                422, "incompatible_attachment", "Choose an image-input model for screenshots."
            )
        input_upper += sum(
            (int(item["width"]) * int(item["height"]) + 255) // 256 + 1024
            for item in image_references
        )
        if input_upper + maximum > model.context_length:
            raise AuthError(
                422,
                "context_limit",
                "Estimated context exceeds this model's limit. "
                "Reduce input or choose another model.",
            )
        prices = {key: Decimal(value) for key, value in model.pricing.items()}
        if not {"prompt", "completion"}.issubset(prices) or any(
            value
            for key, value in prices.items()
            if key not in {"prompt", "completion", "request", "image"}
        ):
            raise AuthError(
                422,
                "unknown_price",
                "A safe estimate is unavailable for this model's billing dimensions.",
            )
        estimate = microusd(
            prices["prompt"] * input_upper
            + prices["completion"] * maximum
            + prices.get("request", Decimal(0))
        )
        if image_references and not model.simulated:
            allowance = allowance_microusd(self.settings.vision_request_allowance_usd)
            if allowance <= 0 or allowance < estimate:
                raise AuthError(
                    422,
                    "vision_allowance_required",
                    "Configure an explicit vision allowance for uncertain image-input pricing.",
                )
            return allowance
        return estimate

    def snapshot(
        self, db: Session, owner: str, body: RunStart, conversation: Conversation
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        head = db.get(Run, conversation.head_run_id) if conversation.head_run_id else None
        if head and head.status not in TERMINAL:
            raise AuthError(409, "conversation_busy", "Wait for or stop the current answer first.")
        prompt = body.prompt.strip()
        turn_ids = list(body.attachment_ids)
        if body.retry_of:
            original = db.get(Run, body.retry_of)
            if (
                not original
                or original.owner_id != owner
                or original.conversation_id != conversation.id
            ):
                raise AuthError(404, "not_found", "Original run not found.")
            if body.attachment_ids:
                raise AuthError(
                    422,
                    "immutable_input",
                    "Repeat saved inputs without replacing their attachments.",
                )
            turn_ids = json.loads(original.settings_json).get("turn_attachment_ids", [])
            messages = json.loads(original.snapshot_json)
            if prompt:
                messages[-1] = self.attachments.turn(db, owner, prompt, turn_ids)
            else:
                prompt = original.prompt
        else:
            messages = json.loads(head.snapshot_json) if head else []
            if head and head.status == "succeeded":
                messages.append({"role": "assistant", "content": head.output})
            elif head:
                messages = messages[:-1]
            messages = [message for message in messages if message["role"] != "system"]
            if body.system_prompt:
                messages.insert(0, {"role": "system", "content": body.system_prompt})
            messages.append(self.attachments.turn(db, owner, prompt, turn_ids))
        references = self.attachments.references(db, owner, messages)
        if len(references) > self.settings.max_upload_files:
            raise AuthError(
                422,
                "file_count",
                "Saved context exceeds the attachment count limit. Start a new conversation.",
            )
        if sum(item.original_size for item in references) > self.settings.max_upload_total_bytes:
            raise AuthError(
                413,
                "upload_size",
                "Saved context exceeds the combined attachment byte limit. Reduce the input.",
            )
        return messages, prompt, turn_ids

    def check_budget(
        self,
        db: Session,
        owner: str,
        reservation: int,
        simulated: bool,
        verification: bool,
        count: int = 1,
    ) -> None:
        now = self.now()
        request_limit = (
            allowance_microusd(self.settings.max_request_usd) if not simulated else 1_000_000
        )
        daily_limit = (
            allowance_microusd(self.settings.daily_budget_usd) if not simulated else 10_000_000
        )
        start_of_day = now // 86400 * 86400
        total = (
            db.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (Charge.actual_microusd.is_not(None), Charge.actual_microusd),
                                else_=Charge.reserved_microusd,
                            )
                        ),
                        0,
                    )
                ).where(
                    Charge.owner_id == owner,
                    or_(
                        Charge.created_at >= start_of_day,
                        Charge.state.in_(["reserved", "uncertain"]),
                    ),
                )
            )
            or 0
        )
        if reservation > request_limit or int(total) + reservation > daily_limit:
            raise AuthError(
                402, "budget_limit", "This request exceeds the configured spending allowance."
            )
        if verification and not simulated:
            verification_total = (
                db.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        Charge.actual_microusd.is_not(None),
                                        Charge.actual_microusd,
                                    ),
                                    else_=Charge.reserved_microusd,
                                )
                            ),
                            0,
                        )
                    ).where(Charge.owner_id == owner, Charge.purpose == "verification")
                )
                or 0
            )
            if int(verification_total) + reservation > allowance_microusd(
                self.settings.live_test_budget_usd
            ):
                raise AuthError(
                    402,
                    "live_test_budget",
                    "The cumulative live verification allowance is exhausted or unconfigured.",
                )
        active = (
            db.scalar(
                select(func.count())
                .select_from(Run)
                .where(Run.status.in_(["queued", "running", "cancel_requested"]))
            )
            or 0
        )
        active += (
            db.scalar(
                select(func.count())
                .select_from(MediaJob)
                .where(MediaJob.status.in_(["queued", "submitting", "running", "cancel_requested"]))
            )
            or 0
        )
        if active + count > self.settings.max_queued_runs:
            raise AuthError(429, "queue_full", "The generation queue is full. Try later.")
        rate_key = digest(f"generation:{owner}")
        bucket = db.get(AuthBucket, rate_key)
        if bucket and now - bucket.window_start >= 60:
            bucket.window_start, bucket.attempts = now, 0
        if bucket and bucket.attempts + count > 20:
            raise AuthError(429, "generation_throttled", "Wait before submitting more generations.")
        if bucket:
            bucket.attempts += count
        else:
            db.add(AuthBucket(key=rate_key, window_start=now, attempts=count))

    def create_queued(
        self,
        db: Session,
        owner: str,
        body: RunStart,
        model: ModelInfo,
        messages: list[dict[str, Any]],
        prompt: str,
        turn_ids: list[str],
        reservation: int,
        comparison_id: str | None = None,
    ) -> Run:
        now = self.now()
        request_hash = digest(json.dumps(body.model_dump(), sort_keys=True))
        run_id = uuid4().hex
        settings = {
            "enqueued_at_ms": time.time_ns() // 1000000,
            "max_tokens": body.max_tokens,
            "temperature": body.temperature,
            "model_name": model.name,
            "simulated": model.simulated,
            "retry_of": body.retry_of,
            "system_prompt": messages[0]["content"]
            if messages and messages[0]["role"] == "system"
            else "",
            "pricing": model.pricing,
            "turn_attachment_ids": turn_ids,
            "attachments": [
                self.attachments.info(item).model_dump()
                for item in self.attachments.references(db, owner, messages)
            ],
            "estimate_kind": "vision_allowance"
            if any(
                message.get("_attachments")
                and any(item["kind"] == "image" for item in message["_attachments"])
                for message in messages
            )
            and not model.simulated
            else "approximate_upper",
        }
        run = Run(
            id=run_id,
            owner_id=owner,
            conversation_id=body.conversation_id,
            model_id=model.id,
            comparison_id=comparison_id,
            turn=int(
                db.scalar(
                    select(func.coalesce(func.max(Run.turn), 0)).where(
                        Run.conversation_id == body.conversation_id
                    )
                )
                or 0
            )
            + 1,
            snapshot_json=json.dumps(messages),
            settings_json=json.dumps(settings),
            prompt=prompt,
            output="",
            status="queued",
            sequence=0,
            created_at=now,
        )
        db.add(run)
        db.flush()
        db.add(
            Charge(
                id=uuid4().hex,
                owner_id=owner,
                idempotency_key=body.idempotency_key,
                request_hash=request_hash,
                run_id=run_id,
                state="reserved",
                reserved_microusd=reservation,
                actual_microusd=None,
                purpose="verification" if body.verification_run else "generation",
                price_json=json.dumps({"model_id": model.id, "pricing": model.pricing}),
                created_at=now,
            )
        )
        for item in self.attachments.references(db, owner, messages):
            db.add(RunAttachment(run_id=run_id, attachment_id=item.id))
        return run

    def validate_model(self, model: ModelInfo, body: RunStart) -> None:
        if "max_tokens" not in model.supported_parameters:
            raise AuthError(
                422,
                "unsupported_parameter",
                "This model does not advertise the required output limit.",
            )
        if body.temperature is not None and "temperature" not in model.supported_parameters:
            raise AuthError(
                422, "unsupported_parameter", "This model does not support temperature."
            )
        if body.max_tokens > self.settings.max_output_tokens or (
            model.max_completion_tokens and body.max_tokens > model.max_completion_tokens
        ):
            raise AuthError(422, "output_limit", "Reduce the output token limit.")

    async def authorize_dispatch(self) -> None:
        if self.closing:
            raise AuthError(503, "shutting_down", "The service is restarting. Try again later.")
        if self.settings.provider_mode == "openrouter" and (
            not self.settings.openrouter_api_key.get_secret_value()
            or self.settings.max_request_usd <= 0
            or self.settings.daily_budget_usd <= 0
        ):
            raise AuthError(
                503,
                "spending_unconfigured",
                "Configure a restricted provider key and approved spending limits.",
            )
        try:
            await self.provider.authorize()
        except ProviderError:
            raise AuthError(
                503,
                "provider_key_rejected",
                "Verify a restricted, non-management provider key with an explicit spend limit.",
            ) from None

    async def start(self, owner: str, body: RunStart) -> RunInfo:
        request_hash = digest(json.dumps(body.model_dump(), sort_keys=True))
        with Session(self.engine) as db:
            existing = self.existing(db, owner, body.idempotency_key, request_hash)
            if existing:
                return existing
        await self.authorize_dispatch()
        models = (await self.catalog.get()).models
        model = next((item for item in models if item.id == body.model_id), None)
        if not model:
            raise AuthError(422, "invalid_model", "Choose a model from the current catalog.")
        self.validate_model(model, body)
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            existing = self.existing(db, owner, body.idempotency_key, request_hash)
            if existing:
                return existing
            conversation = db.get(Conversation, body.conversation_id)
            if not conversation or conversation.owner_id != owner:
                raise AuthError(404, "not_found", "Conversation not found.")
            messages, prompt, turn_ids = self.snapshot(db, owner, body, conversation)
            reservation = self.estimate(model, messages, body.max_tokens)
            if (
                body.request_allowance_microusd is not None
                and reservation > body.request_allowance_microusd
            ):
                raise AuthError(
                    402,
                    "request_allowance",
                    "The estimate exceeds this explicit request allowance.",
                )
            self.check_budget(db, owner, reservation, model.simulated, body.verification_run)
            original = db.get(Run, body.retry_of) if body.retry_of else None
            comparison_id = original.comparison_id if original else None
            if (
                comparison_id
                and original
                and (original.model_id != model.id or original.status not in TERMINAL)
            ):
                raise AuthError(
                    409,
                    "candidate_busy",
                    "Retry a completed candidate with its original model, "
                    "or start a new comparison.",
                )
            run = self.create_queued(
                db, owner, body, model, messages, prompt, turn_ids, reservation, comparison_id
            )
            if comparison_id is None:
                conversation.head_run_id = run.id
            conversation.updated_at = self.now()
            db.commit()
            result = self.info(db, run)
        self.schedule(run.id)
        return result

    def schedule(self, run_id: str) -> None:
        if run_id not in self.tasks and not self.closing:
            task = asyncio.create_task(self.execute(run_id))
            self.tasks[run_id] = task
            task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def recover(self) -> None:
        with Session(self.engine) as db:
            for run in db.scalars(
                select(Run).where(Run.status.in_(["running", "cancel_requested"]))
            ):
                run.status, run.error_code = "interrupted", "billing_unknown"
                run.completed_at, run.sequence = self.now(), run.sequence + 1
                charge = db.scalar(select(Charge).where(Charge.run_id == run.id))
                if charge:
                    charge.state = "uncertain"
            queued = list(db.scalars(select(Run.id).where(Run.status == "queued")))
            db.commit()
        for run_id in queued:
            self.schedule(run_id)

    async def stop(self) -> None:
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.provider.close()

    async def execute(self, run_id: str) -> None:
        async with self.slots:
            output, usage, provider_name, generation_id = "", None, None, None
            start = time.monotonic()
            first_token = None
            providers_seen: list[str] = []
            last_checkpoint = start
            with Session(self.engine) as db:
                run = db.get(Run, run_id)
                if not run or run.status != "queued":
                    return
                owner_id = run.owner_id
                try:
                    compiled = self.attachments.compile(owner_id, json.loads(run.snapshot_json))
                except (AuthError, OSError):
                    run.status, run.error_code, run.completed_at = (
                        "failed",
                        "attachment_unavailable",
                        self.now(),
                    )
                    run.sequence += 1
                    charge = db.scalar(select(Charge).where(Charge.run_id == run_id))
                    if charge:
                        charge.actual_microusd, charge.state = 0, "settled"
                    db.commit()
                    return
                run.status, run.started_at, run.sequence = "running", self.now(), run.sequence + 1
                parameters = json.loads(run.settings_json)
                parameters["queue_delay_ms"] = max(
                    0,
                    time.time_ns() // 1000000
                    - parameters.get("enqueued_at_ms", run.created_at * 1000),
                )
                run.settings_json = json.dumps(parameters)
                prices = parameters["pricing"]
                payload: dict[str, Any] = {
                    "model": run.model_id,
                    "messages": compiled,
                    "stream": True,
                    "max_tokens": parameters["max_tokens"],
                    "provider": {
                        "require_parameters": True,
                        "allow_fallbacks": True,
                        "max_price": {
                            "prompt": Decimal(prices["prompt"]) * 1_000_000,
                            "completion": Decimal(prices["completion"]) * 1_000_000,
                            "request": Decimal(prices.get("request", "0")),
                        },
                    },
                }
                if parameters["temperature"] is not None:
                    payload["temperature"] = parameters["temperature"]
                db.commit()
            status, error = "succeeded", None
            try:
                async for chunk in self.provider.stream(payload):
                    if chunk.text and first_token is None:
                        first_token = int((time.monotonic() - start) * 1000)
                    if len(output) + len(chunk.text) > 131072:
                        raise ProviderError("output_size_limit")
                    output += chunk.text
                    first_generation = chunk.generation_id is not None and generation_id is None
                    changed_provider = (
                        chunk.provider is not None and chunk.provider not in providers_seen
                    )
                    if chunk.provider and changed_provider:
                        providers_seen.append(chunk.provider)
                    usage = sanitized_usage(chunk.usage) if chunk.usage else usage
                    details = usage.get("completion_tokens_details") if usage else None
                    if (
                        usage is not None
                        and isinstance(details, dict)
                        and isinstance(details.get("reasoning_tokens"), int)
                    ):
                        usage["reasoning_tokens"] = details["reasoning_tokens"]
                    if providers_seen:
                        usage = {**(usage or {}), "providers_seen": list(providers_seen)}
                    provider_name = chunk.provider or provider_name
                    generation_id = chunk.generation_id or generation_id
                    if (
                        first_generation
                        or changed_provider
                        or time.monotonic() - last_checkpoint >= 0.25
                    ):
                        self.checkpoint(
                            run_id,
                            output,
                            usage,
                            provider_name,
                            generation_id,
                            first_token,
                            int((time.monotonic() - start) * 1000),
                        )
                        last_checkpoint = time.monotonic()
            except asyncio.CancelledError:
                with Session(self.engine) as db:
                    current = db.get(Run, run_id)
                    status = (
                        "cancelled"
                        if current and current.status == "cancel_requested"
                        else "interrupted"
                    )
                error = "billing_unknown"
            except ProviderError as exc:
                status, error = "failed", exc.code
            except Exception:
                status, error = "failed", "provider_failed"
            self.checkpoint(
                run_id,
                output,
                usage,
                provider_name,
                generation_id,
                first_token,
                int((time.monotonic() - start) * 1000),
                status,
                error,
            )
            if status == "succeeded" and (not usage or usage.get("cost") is None):
                await self.reconcile(owner_id, run_id)

    def checkpoint(
        self,
        run_id: str,
        output: str,
        usage: dict[str, Any] | None,
        provider: str | None,
        generation_id: str | None,
        first_token: int | None,
        elapsed: int,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        with Session(self.engine) as db:
            run = db.get(Run, run_id)
            if not run:
                return
            run.output, run.provider, run.generation_id = output, provider, generation_id
            run.first_token_ms, run.elapsed_ms = first_token, elapsed
            run.usage_json = json.dumps(usage, default=str) if usage else None
            run.sequence += 1
            charge = db.scalar(select(Charge).where(Charge.run_id == run_id))
            if charge:
                price_snapshot = json.loads(charge.price_json)
                if "pricing" not in price_snapshot:
                    price_snapshot = {"pricing": price_snapshot}
                price_snapshot.update(
                    model_id=run.model_id,
                    generation_id=generation_id or price_snapshot.get("generation_id"),
                    provider=provider or price_snapshot.get("provider"),
                )
                charge.price_json = json.dumps(price_snapshot)
            if status:
                run.status, run.error_code, run.completed_at = status, error, self.now()
                if charge:
                    try:
                        actual = (
                            microusd(Decimal(str(usage["cost"])))
                            if status == "succeeded" and usage and usage.get("cost") is not None
                            else None
                        )
                    except (ValueError, ArithmeticError):
                        actual = None
                    charge.actual_microusd = actual
                    charge.state = "settled" if actual is not None else "uncertain"
            db.commit()

    def cancel(self, owner: str, run_id: str) -> RunInfo:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            run = db.get(Run, run_id)
            if not run or run.owner_id != owner:
                raise AuthError(404, "not_found", "Run not found.")
            if run.status == "queued":
                run.status, run.completed_at = "cancelled", self.now()
                charge = db.scalar(select(Charge).where(Charge.run_id == run_id))
                if charge:
                    charge.actual_microusd, charge.state = 0, "settled"
            elif run.status == "running":
                run.status = "cancel_requested"
            run.sequence += 1
            db.commit()
            return self.info(db, run)

    async def cancel_task(self, owner: str, run_id: str) -> RunInfo:
        self.cancel(owner, run_id)
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.get(owner, run_id)

    async def reconcile(self, owner: str, run_id: str) -> RunInfo:
        before = self.get(owner, run_id)
        if (
            before.accounting_state == "settled"
            or before.status not in TERMINAL
            or not before.generation_id
        ):
            return before
        now = self.now()
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            key = digest(f"reconcile:{run_id}")
            bucket = db.get(AuthBucket, key)
            if bucket and now - bucket.window_start < 60:
                return before
            if bucket:
                bucket.window_start, bucket.attempts = now, 1
            else:
                db.add(AuthBucket(key=key, window_start=now, attempts=1))
            db.commit()
        try:
            data = await self.provider.generation(before.generation_id)
            if not data or data.get("id") != before.generation_id or data.get("total_cost") is None:
                return before
            actual = microusd(Decimal(str(data["total_cost"])))
        except (ProviderError, ValueError, ArithmeticError):
            return before
        with Session(self.engine) as db:
            charge = db.scalar(
                select(Charge).where(Charge.run_id == run_id, Charge.owner_id == owner)
            )
            run = db.get(Run, run_id)
            if charge and run:
                charge.actual_microusd, charge.state = actual, "settled"
                usage = json.loads(run.usage_json) if run.usage_json else {}
                usage["cost"] = str(data["total_cost"])
                usage["source"] = "generation_metadata"
                for source, target in [
                    ("tokens_prompt", "prompt_tokens"),
                    ("tokens_completion", "completion_tokens"),
                    ("native_tokens_reasoning", "reasoning_tokens"),
                ]:
                    if isinstance(data.get(source), int):
                        usage[target] = data[source]
                run.usage_json, run.sequence = json.dumps(usage), run.sequence + 1
                db.commit()
        return self.get(owner, run_id)

    def fork(self, owner: str, source_id: str) -> str:
        self.attachments.check_space()
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            source = db.get(Run, source_id)
            if not source or source.owner_id != owner or source.status != "succeeded":
                raise AuthError(422, "answer_unavailable", "Choose a completed answer to continue.")
            original = self.info(db, source)
            conversation = Conversation(
                id=uuid4().hex,
                owner_id=owner,
                title=f"Continued: {source.prompt[:70]}",
                created_at=self.now(),
                updated_at=self.now(),
            )
            db.add(conversation)
            db.flush()
            settings = json.loads(source.settings_json)
            settings.update(
                imported_from=source.id,
                original_actual_microusd=original.actual_microusd,
                source_created_at=source.created_at,
            )
            clone = Run(
                id=uuid4().hex,
                owner_id=owner,
                conversation_id=conversation.id,
                comparison_id=None,
                model_id=source.model_id,
                turn=1,
                snapshot_json=source.snapshot_json,
                settings_json=json.dumps(settings),
                prompt=source.prompt,
                output=source.output,
                status="succeeded",
                error_code=None,
                provider=source.provider,
                generation_id=source.generation_id,
                usage_json=source.usage_json,
                sequence=1,
                created_at=self.now(),
                started_at=source.started_at,
                completed_at=source.completed_at,
                first_token_ms=source.first_token_ms,
                elapsed_ms=source.elapsed_ms,
            )
            db.add(clone)
            db.flush()
            for asset in self.attachments.references(db, owner, json.loads(source.snapshot_json)):
                db.add(RunAttachment(run_id=clone.id, attachment_id=asset.id))
            conversation.head_run_id = clone.id
            db.commit()
            return conversation.id
