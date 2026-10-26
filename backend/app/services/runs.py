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
from app.models import AuthBucket, Charge, Conversation, Run
from app.providers.chat import ChatProvider, ProviderError
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
    ) -> None:
        self.engine, self.settings, self.provider, self.catalog, self.now = (
            engine,
            settings,
            provider,
            catalog,
            now,
        )
        self.slots = asyncio.Semaphore(2)
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.closing = False

    def info(self, db: Session, run: Run) -> RunInfo:
        charge = db.scalar(select(Charge).where(Charge.run_id == run.id))
        if not charge:
            raise AuthError(500, "accounting_unavailable", "Usage accounting is unavailable.")
        settings = json.loads(run.settings_json)
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
            reserved_microusd=charge.reserved_microusd,
            actual_microusd=charge.actual_microusd,
            accounting_state=charge.state,
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
        if input_upper + maximum > model.context_length:
            raise AuthError(
                422,
                "context_limit",
                "Estimated context exceeds this model's limit. "
                "Reduce input or choose another model.",
            )
        prices = {key: Decimal(value) for key, value in model.pricing.items()}
        if not {"prompt", "completion"}.issubset(prices) or any(
            value for key, value in prices.items() if key not in {"prompt", "completion", "request"}
        ):
            raise AuthError(
                422,
                "unknown_price",
                "A safe estimate is unavailable for this model's billing dimensions.",
            )
        return microusd(
            prices["prompt"] * input_upper
            + prices["completion"] * maximum
            + prices.get("request", Decimal(0))
        )

    async def start(self, owner: str, body: RunStart) -> RunInfo:
        request_hash = digest(json.dumps(body.model_dump(), sort_keys=True))
        with Session(self.engine) as db:
            existing = self.existing(db, owner, body.idempotency_key, request_hash)
            if existing:
                return existing
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
        models = (await self.catalog.get()).models
        model = next((item for item in models if item.id == body.model_id), None)
        if not model:
            raise AuthError(422, "invalid_model", "Choose a model from the current catalog.")
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
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            existing = self.existing(db, owner, body.idempotency_key, request_hash)
            if existing:
                return existing
            conversation = db.get(Conversation, body.conversation_id)
            if not conversation or conversation.owner_id != owner:
                raise AuthError(404, "not_found", "Conversation not found.")
            head = db.get(Run, conversation.head_run_id) if conversation.head_run_id else None
            if head and head.status not in TERMINAL:
                raise AuthError(
                    409, "conversation_busy", "Wait for or stop the current answer first."
                )
            prompt = body.prompt.strip()
            if body.retry_of:
                original = db.get(Run, body.retry_of)
                if (
                    not original
                    or original.owner_id != owner
                    or original.conversation_id != conversation.id
                ):
                    raise AuthError(404, "not_found", "Original run not found.")
                messages = json.loads(original.snapshot_json)
                if prompt:
                    messages[-1] = {"role": "user", "content": prompt}
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
                messages.append({"role": "user", "content": prompt})
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
            now = self.now()
            request_limit = (
                allowance_microusd(self.settings.max_request_usd)
                if not model.simulated
                else 1_000_000
            )
            daily_limit = (
                allowance_microusd(self.settings.daily_budget_usd)
                if not model.simulated
                else 10_000_000
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
            if body.verification_run and not model.simulated:
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
            if active >= self.settings.max_queued_runs:
                raise AuthError(429, "queue_full", "The generation queue is full. Try later.")
            rate_key = digest(f"generation:{owner}")
            bucket = db.get(AuthBucket, rate_key)
            if bucket and now - bucket.window_start >= 60:
                bucket.window_start, bucket.attempts = now, 0
            if bucket and bucket.attempts >= 20:
                raise AuthError(
                    429, "generation_throttled", "Wait before submitting more generations."
                )
            if bucket:
                bucket.attempts += 1
            else:
                db.add(AuthBucket(key=rate_key, window_start=now, attempts=1))
            run_id = uuid4().hex
            settings = {
                "max_tokens": body.max_tokens,
                "temperature": body.temperature,
                "model_name": model.name,
                "simulated": model.simulated,
                "retry_of": body.retry_of,
                "system_prompt": messages[0]["content"]
                if messages and messages[0]["role"] == "system"
                else "",
                "pricing": model.pricing,
            }
            run = Run(
                id=run_id,
                owner_id=owner,
                conversation_id=conversation.id,
                model_id=model.id,
                turn=int(
                    db.scalar(
                        select(func.coalesce(func.max(Run.turn), 0)).where(
                            Run.conversation_id == conversation.id
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
                    price_json=json.dumps(model.pricing),
                    created_at=now,
                )
            )
            conversation.head_run_id, conversation.updated_at = run_id, now
            db.commit()
            result = self.info(db, run)
        self.schedule(run_id)
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
                run.status, run.started_at, run.sequence = "running", self.now(), run.sequence + 1
                owner_id = run.owner_id
                parameters = json.loads(run.settings_json)
                prices = parameters["pricing"]
                payload: dict[str, Any] = {
                    "model": run.model_id,
                    "messages": json.loads(run.snapshot_json),
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
            if status:
                run.status, run.error_code, run.completed_at = status, error, self.now()
                charge = db.scalar(select(Charge).where(Charge.run_id == run_id))
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
