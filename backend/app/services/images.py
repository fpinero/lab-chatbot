"""Durable image jobs sharing the chat spending ledger and generation slots."""

import asyncio
import base64
import binascii
import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import AuthError, digest
from app.models import Charge, MediaAsset, MediaJob, MediaJobAttachment
from app.providers.chat import ProviderError
from app.providers.images import ImageProvider
from app.services.attachments import AttachmentInfo
from app.services.image_catalog import ImageCatalog, ImageEndpoint, ImageEndpointInfo
from app.services.runs import RunService, allowance_microusd, microusd, sanitized_usage

ACTIVE = {"queued", "submitting", "running", "cancel_requested"}
OPTION_KEYS = {"resolution", "aspect_ratio", "quality", "output_format"}
RASTER = {"png", "jpeg", "webp"}


class ImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=200)
    provider_tag: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=12000)
    options: dict[str, str] = Field(default_factory=dict, max_length=4)
    count: int = Field(default=1, ge=1, le=4)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    verification_run: bool = False
    request_allowance_microusd: int | None = Field(default=None, ge=0, le=100000000)


class ImageStart(ImageInput):
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")
    retry_of: str | None = Field(default=None, max_length=64)
    acknowledge_duplicate_risk: bool = False


class ImageQuote(BaseModel):
    spend_control: Literal["application", "provider"] = "application"
    estimated_microusd: int | None
    reservation_microusd: int | None
    uncertain: bool
    ready: bool
    reason: str | None


class MediaAssetInfo(BaseModel):
    id: str
    mime: str
    size: int
    width: int
    height: int
    expires_at: int


class MediaJobInfo(BaseModel):
    id: str
    family: Literal["images"] = "images"
    model_id: str
    model_name: str
    provider_name: str
    provider_tag: str
    prompt: str
    options: dict[str, str]
    count: int
    attachments: list[AttachmentInfo]
    status: str
    error_code: str | None
    generation_id: str | None
    accounting_state: str
    estimated_microusd: int | None
    reserved_microusd: int
    actual_microusd: int | None
    uncertain_estimate: bool
    created_at: int
    started_at: int | None
    completed_at: int | None
    queue_delay_ms: int | None
    elapsed_ms: int | None
    simulated: bool
    usage: dict[str, Any] | None
    assets: list[MediaAssetInfo]


class ImageService:
    def __init__(self, runs: RunService, provider: ImageProvider, catalog: ImageCatalog) -> None:
        self.runs, self.provider, self.catalog = runs, provider, catalog
        self.engine, self.settings, self.now = runs.engine, runs.settings, runs.now
        self.files = runs.attachments
        self.root = (self.settings.data_dir / "media").resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.closing = False

    def info(self, db: Session, job: MediaJob) -> MediaJobInfo:
        charge = db.get(Charge, job.charge_id)
        if not charge:
            raise AuthError(500, "accounting_unavailable", "Usage accounting is unavailable.")
        saved = json.loads(job.settings_json)
        body = ImageStart.model_validate_json(job.request_json)
        assets = db.scalars(
            select(MediaAsset).where(
                MediaAsset.job_id == job.id, MediaAsset.expires_at > self.now()
            )
        )
        return MediaJobInfo(
            id=job.id,
            model_id=job.model_id,
            model_name=saved["model_name"],
            provider_name=saved["provider_name"],
            provider_tag=body.provider_tag,
            prompt=job.prompt,
            options=body.options,
            count=body.count,
            attachments=[AttachmentInfo.model_validate(item) for item in saved["attachments"]],
            status=job.status,
            error_code=job.error_code,
            generation_id=job.generation_id,
            accounting_state=charge.state,
            estimated_microusd=saved["estimated_microusd"],
            reserved_microusd=charge.reserved_microusd,
            actual_microusd=charge.actual_microusd,
            uncertain_estimate=saved["uncertain"],
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            queue_delay_ms=saved.get("queue_delay_ms"),
            elapsed_ms=saved.get("elapsed_ms"),
            simulated=saved["simulated"],
            usage=json.loads(job.usage_json) if job.usage_json else None,
            assets=[
                MediaAssetInfo(
                    id=item.id,
                    mime=item.mime,
                    size=item.size,
                    width=item.width,
                    height=item.height,
                    expires_at=item.expires_at,
                )
                for item in assets
            ],
        )

    def owned(self, db: Session, owner: str, identifier: str) -> MediaJob:
        job = db.get(MediaJob, identifier)
        if not job or job.owner_id != owner or job.family != "images":
            raise AuthError(404, "not_found", "Image job not found.")
        return job

    def get(self, owner: str, identifier: str) -> MediaJobInfo:
        with Session(self.engine) as db:
            return self.info(db, self.owned(db, owner, identifier))

    def history(self, owner: str) -> list[MediaJobInfo]:
        with Session(self.engine) as db:
            return [
                self.info(db, job)
                for job in db.scalars(
                    select(MediaJob)
                    .where(MediaJob.owner_id == owner, MediaJob.family == "images")
                    .order_by(MediaJob.created_at.desc(), MediaJob.id)
                    .limit(100)
                )
            ]

    def validate(self, body: ImageInput, details: ImageEndpointInfo) -> ImageEndpoint:
        endpoint = next(
            (item for item in details.endpoints if item.provider_tag == body.provider_tag), None
        )
        if not endpoint or not body.prompt.strip():
            raise AuthError(
                422, "invalid_provider", "Choose a current image provider and enter a prompt."
            )
        for key, value in body.options.items():
            capability = endpoint.parameters.get(key)
            if (
                key not in OPTION_KEYS
                or not capability
                or capability.type != "enum"
                or value not in capability.values
            ):
                raise AuthError(
                    422,
                    "unsupported_parameter",
                    "Use only the selected provider's advertised image settings.",
                )
            if key == "output_format" and value not in RASTER:
                raise AuthError(
                    422, "unsupported_format", "Only PNG, JPEG and WebP outputs are supported."
                )
        formats = endpoint.parameters.get("output_format")
        if formats and formats.type == "enum" and not RASTER.intersection(formats.values):
            raise AuthError(
                422, "unsupported_format", "This endpoint does not advertise raster output."
            )
        if formats and "output_format" not in body.options:
            raise AuthError(
                422, "output_format_required", "Choose an advertised raster output format."
            )
        count = endpoint.parameters.get("n")
        if (
            body.count > self.settings.max_generated_images
            or (body.count != 1 and (not count or count.type != "range"))
            or (
                count
                and (
                    count.type != "range"
                    or count.min is None
                    or count.max is None
                    or not count.min <= body.count <= count.max
                )
            )
        ):
            raise AuthError(422, "image_count", "Reduce the image count to the advertised range.")
        if body.attachment_ids:
            references = endpoint.parameters.get("input_references")
            if (
                "image" not in details.model.input_modalities
                or not references
                or references.type not in {"boolean", "range"}
            ):
                raise AuthError(
                    422,
                    "incompatible_attachment",
                    "This endpoint does not advertise reference-image support.",
                )
            if references.type == "range" and (
                references.min is None
                or references.max is None
                or not references.min <= len(body.attachment_ids) <= references.max
            ):
                raise AuthError(422, "file_count", "Use the advertised reference-image count.")
        return endpoint

    def quote(self, body: ImageInput, endpoint: ImageEndpoint, simulated: bool) -> ImageQuote:
        known = Decimal(0)
        uncertain = not endpoint.pricing
        for line in endpoint.pricing:
            if line.unit in {"image", "request"} and line.billable in {
                "output_image",
                "input_image",
                "input_reference",
            }:
                units = (
                    body.count if line.billable == "output_image" else len(set(body.attachment_ids))
                )
                known += line.cost_usd * (units if line.unit == "image" else 1)
            elif line.cost_usd:
                uncertain = True
        estimated = microusd(known) if not uncertain else None
        provider_control = self.settings.spend_control == "provider" and not simulated
        allowance = allowance_microusd(self.settings.image_request_allowance_usd)
        if provider_control:
            allowance = self.runs.provider_remainder()
        reservation = allowance if uncertain and (allowance or provider_control) else estimated
        if simulated and reservation is None:
            reservation = 1000
        reason = None
        if provider_control and (allowance <= 0 or (reservation or 0) > allowance):
            reason = "The estimate exceeds the remaining OpenRouter key budget."
        elif reservation is None:
            reason = "Configure an approved image request allowance for uncertain pricing."
        elif reservation < microusd(known):
            reason = "The configured image allowance is below known billing dimensions."
        elif (
            body.request_allowance_microusd is not None
            and reservation > body.request_allowance_microusd
        ):
            reason = "The estimate exceeds this explicit request allowance."
        elif (
            not simulated
            and self.settings.spend_control == "application"
            and (self.settings.max_request_usd <= 0 or self.settings.daily_budget_usd <= 0)
        ):
            reason = "Configure approved request and daily spending limits."
        return ImageQuote(
            spend_control=self.settings.spend_control,
            estimated_microusd=estimated,
            reservation_microusd=reservation,
            uncertain=uncertain,
            ready=reason is None,
            reason=reason,
        )

    def snapshot(
        self, db: Session, owner: str, body: ImageInput
    ) -> tuple[list[dict[str, Any]], list[AttachmentInfo]]:
        turn = self.files.turn(db, owner, body.prompt, body.attachment_ids)
        references = self.files.references(db, owner, [turn])
        if any(item.kind != "image" for item in references):
            raise AuthError(
                422,
                "incompatible_attachment",
                "Image generation accepts screenshot references only.",
            )
        if sum(item.original_size for item in references) > self.settings.max_upload_total_bytes:
            raise AuthError(
                413, "upload_size", "Reference images exceed the combined attachment limit."
            )
        return [turn], [self.files.info(item) for item in references]

    async def preview(self, owner: str, body: ImageInput) -> ImageQuote:
        if self.settings.spend_control == "provider":
            await self.runs.refresh_provider_budget()
        details = await self.catalog.endpoints(body.model_id)
        endpoint = self.validate(body, details)
        with Session(self.engine) as db:
            self.snapshot(db, owner, body)
        return self.quote(body, endpoint, details.model.simulated)

    def existing(
        self, db: Session, owner: str, body: ImageStart, fingerprint: str
    ) -> MediaJobInfo | None:
        charge = db.scalar(
            select(Charge).where(
                Charge.owner_id == owner, Charge.idempotency_key == body.idempotency_key
            )
        )
        if not charge:
            return None
        if charge.request_hash != fingerprint:
            raise AuthError(
                409, "idempotency_conflict", "This submission key belongs to another request."
            )
        job = db.scalar(select(MediaJob).where(MediaJob.charge_id == charge.id))
        if not job:
            raise AuthError(
                410,
                "job_deleted",
                "The original job was deleted. Submit deliberately with a new key.",
            )
        return self.info(db, job)

    async def start(self, owner: str, body: ImageStart) -> MediaJobInfo:
        fingerprint = digest(json.dumps(body.model_dump(), sort_keys=True))
        with Session(self.engine) as db:
            existing = self.existing(db, owner, body, fingerprint)
            if existing:
                return existing
        await self.runs.authorize_dispatch()
        try:
            await self.provider.authorize()
        except ProviderError:
            raise AuthError(
                503, "provider_key_rejected", "Verify a restricted provider key first."
            ) from None
        details = await self.catalog.endpoints(body.model_id)
        endpoint = self.validate(body, details)
        quote = self.quote(body, endpoint, details.model.simulated)
        if not quote.ready or quote.reservation_microusd is None:
            raise AuthError(
                402,
                "image_allowance_required",
                quote.reason or "Configure an approved image allowance.",
            )
        if self.closing:
            raise AuthError(503, "shutting_down", "The service is restarting. Try later.")
        self.files.check_space(body.count * self.settings.max_media_file_bytes)
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            existing = self.existing(db, owner, body, fingerprint)
            if existing:
                return existing
            if body.retry_of:
                original = self.owned(db, owner, body.retry_of)
                if original.status in ACTIVE:
                    raise AuthError(409, "job_busy", "Wait for the original image job.")
                original_charge = db.get(Charge, original.charge_id)
                if (
                    original_charge
                    and original_charge.state == "uncertain"
                    and not body.acknowledge_duplicate_risk
                ):
                    raise AuthError(
                        409,
                        "duplicate_spend_risk",
                        "Acknowledge that the earlier request may still charge before retrying.",
                    )
            snapshot, references = self.snapshot(db, owner, body)
            self.runs.check_budget(
                db,
                owner,
                quote.reservation_microusd,
                details.model.simulated,
                body.verification_run,
            )
            charge = Charge(
                id=uuid4().hex,
                owner_id=owner,
                idempotency_key=body.idempotency_key,
                request_hash=fingerprint,
                state="reserved",
                reserved_microusd=quote.reservation_microusd,
                purpose="verification" if body.verification_run else "generation",
                price_json=json.dumps(
                    {
                        "api_family": "images",
                        "model_id": body.model_id,
                        "provider": endpoint.provider_tag,
                        "pricing": [line.model_dump(mode="json") for line in endpoint.pricing],
                    }
                ),
                created_at=self.now(),
            )
            db.add(charge)
            db.flush()
            job = MediaJob(
                id=uuid4().hex,
                owner_id=owner,
                charge_id=charge.id,
                family="images",
                model_id=body.model_id,
                prompt=body.prompt,
                request_json=body.model_dump_json(),
                settings_json=json.dumps(
                    {
                        "model_name": details.model.name,
                        "provider_name": endpoint.provider_name,
                        "simulated": details.model.simulated,
                        "snapshot": snapshot,
                        "attachments": [item.model_dump() for item in references],
                        "estimated_microusd": quote.estimated_microusd,
                        "uncertain": quote.uncertain,
                        "send_count": "n" in endpoint.parameters,
                        "enqueued_at_ms": time.time_ns() // 1000000,
                    }
                ),
                status="queued",
                created_at=self.now(),
            )
            db.add(job)
            db.flush()
            for item in references:
                db.add(MediaJobAttachment(job_id=job.id, attachment_id=item.id))
            db.commit()
            result = self.info(db, job)
        self.schedule(result.id)
        return result

    def schedule(self, identifier: str) -> None:
        if identifier not in self.tasks and not self.closing:
            task = asyncio.create_task(self.execute(identifier))
            self.tasks[identifier] = task
            task.add_done_callback(lambda _: self.tasks.pop(identifier, None))

    def generation(self, identifier: str, generation: str) -> None:
        with Session(self.engine) as db:
            job = db.get(MediaJob, identifier)
            if job and len(generation) <= 200:
                job.generation_id = generation
                charge = db.get(Charge, job.charge_id)
                if charge:
                    snapshot = json.loads(charge.price_json)
                    snapshot["generation_id"] = generation
                    charge.price_json = json.dumps(snapshot)
                db.commit()

    def record_usage(self, identifier: str, raw: Any) -> None:
        usage = sanitized_usage(raw) if isinstance(raw, dict) else {}
        with Session(self.engine) as db:
            job = db.get(MediaJob, identifier)
            if not job:
                return
            job.usage_json = json.dumps(usage)
            charge = db.get(Charge, job.charge_id)
            if charge:
                charge.actual_microusd = (
                    microusd(Decimal(usage["cost"])) if "cost" in usage else None
                )
                charge.state = "settled" if charge.actual_microusd is not None else "uncertain"
            db.commit()

    def finish(
        self, identifier: str, status: str, error: str | None = None, before_dispatch: bool = False
    ) -> None:
        with Session(self.engine) as db:
            job = db.get(MediaJob, identifier)
            if not job:
                return
            job.status, job.error_code, job.completed_at = status, error, self.now()
            saved = json.loads(job.settings_json)
            saved["elapsed_ms"] = max(
                0, time.time_ns() // 1000000 - saved.get("started_at_ms", time.time_ns() // 1000000)
            )
            job.settings_json = json.dumps(saved)
            charge = db.get(Charge, job.charge_id)
            if charge and before_dispatch:
                charge.actual_microusd, charge.state = 0, "settled"
            elif charge and charge.state == "reserved":
                charge.state = "uncertain"
            db.commit()

    async def execute(self, identifier: str) -> None:
        async with self.runs.slots:
            with Session(self.engine) as db:
                job = db.get(MediaJob, identifier)
                if not job or job.status != "queued":
                    return
                owner, saved = job.owner_id, json.loads(job.settings_json)
                body = ImageStart.model_validate_json(job.request_json)
            try:
                compiled = self.files.compile(owner, saved["snapshot"])
                payload: dict[str, Any] = {
                    "model": body.model_id,
                    "prompt": body.prompt,
                    "provider": {"only": [body.provider_tag], "allow_fallbacks": False},
                    **body.options,
                }
                if saved["send_count"]:
                    payload["n"] = body.count
                if body.attachment_ids:
                    payload["input_references"] = compiled[0]["content"][1:]
                if len(json.dumps(payload).encode()) > self.settings.max_provider_payload_bytes:
                    raise AuthError(
                        413,
                        "provider_payload_limit",
                        "Reference image payload exceeds the provider byte ceiling.",
                    )
                self.files.check_space(body.count * self.settings.max_media_file_bytes)
            except (AuthError, OSError):
                self.finish(identifier, "failed", "input_unavailable", before_dispatch=True)
                return
            with Session(self.engine) as db:
                job = db.get(MediaJob, identifier)
                if not job or job.status != "queued":
                    return
                stamp = time.time_ns() // 1000000
                saved.update(
                    started_at_ms=stamp, queue_delay_ms=max(0, stamp - saved["enqueued_at_ms"])
                )
                job.settings_json, job.status, job.started_at = (
                    json.dumps(saved),
                    "submitting",
                    self.now(),
                )
                db.commit()
            try:
                result = await self.provider.generate(
                    payload, lambda value: self.generation(identifier, value)
                )
                self.record_usage(identifier, result.get("usage"))
                await self.publish(identifier, result.get("data"), body.count)
                self.finish(identifier, "succeeded")
            except asyncio.CancelledError:
                self.finish(identifier, "submission_unknown", "billing_unknown")
                raise
            except ProviderError as exc:
                self.finish(
                    identifier,
                    "submission_unknown" if exc.code == "submission_unknown" else "failed",
                    exc.code,
                )
            except (AuthError, OSError, ValueError, TypeError, KeyError):
                self.finish(identifier, "failed", "invalid_media_output")
            except Exception:
                self.finish(identifier, "failed", "image_generation_failed")

    async def publish(self, identifier: str, data: Any, count: int) -> None:
        if not isinstance(data, list) or not 1 <= len(data) <= count:
            raise ProviderError("provider_invalid_response")
        with TemporaryDirectory(prefix="image-", dir=self.files.work) as directory:
            prepared = []
            for index, item in enumerate(data):
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("b64_json"), str)
                    or item.get("url")
                ):
                    raise ProviderError("provider_invalid_response")
                encoded = item["b64_json"]
                if len(encoded) > (self.settings.max_media_file_bytes + 2) // 3 * 4:
                    raise ProviderError("provider_response_limit")
                try:
                    binary = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    raise ProviderError("provider_invalid_response") from None
                extension = (
                    ".png"
                    if binary.startswith(b"\x89PNG\r\n\x1a\n")
                    else ".jpg"
                    if binary.startswith(b"\xff\xd8\xff")
                    else ".webp"
                    if binary[:4] == b"RIFF" and binary[8:12] == b"WEBP"
                    else None
                )
                mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(
                    extension or ""
                )
                if (
                    not extension
                    or item.get("media_type", mime) != mime
                    or len(binary) > self.settings.max_media_file_bytes
                ):
                    raise ProviderError("provider_invalid_response")
                source, output = (
                    Path(directory) / f"source-{index}",
                    Path(directory) / f"output-{index}.webp",
                )
                source.write_bytes(binary)
                async with self.files.parser_slot:
                    parsed = await asyncio.to_thread(
                        self.files.parse, source, output, extension, {"edge": 8192, "resize": 0}
                    )
                if output.stat().st_size > self.settings.max_media_file_bytes:
                    raise ProviderError("provider_response_limit")
                prepared.append((output, parsed))
            published: list[Path] = []
            with self.files.file_lock:
                self.files.check_space(sum(path.stat().st_size for path, _ in prepared))
                try:
                    with Session(self.engine) as db:
                        for path, parsed in prepared:
                            asset_id = uuid4().hex
                            target = self.root / f"{asset_id}.webp"
                            os.replace(path, target)
                            target.chmod(0o600)
                            published.append(target)
                            db.add(
                                MediaAsset(
                                    id=asset_id,
                                    job_id=identifier,
                                    storage_name=target.name,
                                    mime="image/webp",
                                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                    size=target.stat().st_size,
                                    width=parsed["width"],
                                    height=parsed["height"],
                                    created_at=self.now(),
                                    expires_at=self.now()
                                    + self.settings.media_retention_days * 86400,
                                )
                            )
                        db.commit()
                except Exception:
                    for path in published:
                        path.unlink(missing_ok=True)
                    raise

    def asset(self, owner: str, identifier: str) -> tuple[Path, MediaAssetInfo]:
        with Session(self.engine) as db:
            item = db.get(MediaAsset, identifier)
            if not item or item.expires_at <= self.now():
                raise AuthError(404, "not_found", "Media asset not found or expired.")
            self.owned(db, owner, item.job_id)
            path = (self.root / item.storage_name).resolve()
            if path.parent != self.root or not path.is_file():
                raise AuthError(404, "not_found", "Media asset is unavailable.")
            return path, MediaAssetInfo(
                id=item.id,
                mime=item.mime,
                size=item.size,
                width=item.width,
                height=item.height,
                expires_at=item.expires_at,
            )

    def collect(self) -> None:
        with self.files.file_lock, Session(self.engine) as db:
            assets = list(db.scalars(select(MediaAsset).where(MediaAsset.expires_at <= self.now())))
            paths = [self.root / item.storage_name for item in assets]
            for item in assets:
                db.delete(item)
            db.commit()
            for path in paths:
                if path.resolve().parent == self.root:
                    path.unlink(missing_ok=True)

    def remove(self, owner: str, identifier: str) -> None:
        with self.files.file_lock, Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            job = self.owned(db, owner, identifier)
            if job.status in ACTIVE:
                raise AuthError(
                    409, "job_busy", "Wait for the active image job before deleting it."
                )
            paths = [
                self.root / item.storage_name
                for item in db.scalars(select(MediaAsset).where(MediaAsset.job_id == identifier))
            ]
            references = list(
                db.scalars(
                    select(MediaJobAttachment.attachment_id).where(
                        MediaJobAttachment.job_id == identifier
                    )
                )
            )
            db.delete(job)
            db.commit()
            for path in paths:
                if path.resolve().parent == self.root:
                    path.unlink(missing_ok=True)
        self.files.collect(references)

    async def recover(self) -> None:
        with Session(self.engine) as db:
            records = list(
                db.execute(
                    select(MediaJob.id, MediaJob.status).where(
                        MediaJob.family == "images", MediaJob.status.in_(ACTIVE)
                    )
                )
            )
        for identifier, status in records:
            if status == "queued":
                self.schedule(identifier)
            else:
                self.finish(identifier, "submission_unknown", "billing_unknown")

    async def stop(self) -> None:
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.provider.close()
