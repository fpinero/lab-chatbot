"""Volatile chat workers. Only opaque accounting metadata reaches persistent storage."""

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.auth.service import AuthError, digest
from app.models import (
    Attachment,
    Base,
    Charge,
    Conversation,
    Owner,
    OwnerSession,
    Run,
    RunAttachment,
)
from app.services.attachments import MESSAGES, MIMES, AttachmentInfo, AttachmentService
from app.services.catalog import ModelInfo
from app.services.runs import RunInfo, RunService, RunStart


class MemoryAttachments(AttachmentService):
    def __init__(self, worker: "TemporaryWorker", main: RunService) -> None:
        # Do not initialize the disk-backed parent or create any private directories.
        self.engine, self.settings, self.now = worker.engine, main.settings, main.now
        self.worker = worker
        self.upload_slots, self.parser_slot = (
            main.attachments.upload_slots,
            main.attachments.parser_slot,
        )
        self.file_lock = threading.RLock()
        self.blobs: dict[str, bytes] = {}

    def content(self, item: Attachment) -> bytes:
        value = self.blobs.get(item.id)
        if value is None:
            raise AuthError(
                410, "temporary_expired", "This temporary attachment is no longer available."
            )
        return value

    def check_space(self, addition: int = 0) -> None:
        if (
            len(self.blobs) >= 50
            or sum(map(len, self.blobs.values())) + addition > 25 * 1024 * 1024
        ):
            raise AuthError(
                413,
                "temporary_capacity",
                "Temporary attachments exceed the 25 MiB memory limit. Start a new temporary chat.",
            )

    def prepare(self, encoded: str, extension: str) -> dict[str, Any]:
        limits = {
            "pixels": self.settings.max_image_pixels,
            "edge": self.settings.max_image_edge,
            "pages": self.settings.max_pdf_pages,
            "characters": self.settings.max_document_characters,
        }
        try:
            result = subprocess.run(  # noqa: S603, fixed isolated module; payload uses pipes only
                [sys.executable, "-m", "app.services.extractor", "--memory"],
                input=json.dumps(
                    {"data": encoded, "extension": extension, "limits": limits}
                ).encode(),
                capture_output=True,
                timeout=10,
                check=False,
                cwd=Path(__file__).resolve().parents[2],
                env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
                raise ValueError
            parsed = json.loads(result.stdout)
            if not parsed.get("ok"):
                code = parsed.get("code", "invalid_document")
                raise AuthError(
                    422, code, MESSAGES.get(code, "The file could not be safely processed.")
                )
            return dict(parsed)
        except (ValueError, subprocess.TimeoutExpired):
            raise AuthError(
                422, "processing_limit", "This file exceeds processing limits."
            ) from None

    async def upload_memory(self, files: list[dict[str, str]]) -> list[AttachmentInfo]:
        if not 1 <= len(files) <= self.settings.max_upload_files:
            raise AuthError(422, "file_count", "Choose between one and five files.")
        total = 0
        prepared = []
        for file in files:
            try:
                raw = base64.b64decode(file["data"], validate=True)
            except ValueError:
                raise AuthError(422, "invalid_upload", "Invalid file encoding.") from None
            total += len(raw)
            if (
                len(raw) > self.settings.max_upload_file_bytes
                or total > self.settings.max_upload_total_bytes
            ):
                raise AuthError(413, "upload_size", "Upload exceeds the file or batch byte limit.")
            name, extension = self.validate_name(file["name"], file["mime"], raw[:16])
            async with self.parser_slot:
                parsed = await asyncio.to_thread(self.prepare, file["data"], extension)
            data = base64.b64decode(parsed.pop("data"), validate=True)
            if len(data) > self.settings.max_upload_file_bytes:
                raise AuthError(413, "upload_size", "Normalized file exceeds the byte limit.")
            prepared.append((name, extension, len(raw), parsed, data))
        self.check_space(sum(len(row[4]) for row in prepared))
        if len(self.blobs) + len(prepared) > 50:
            raise AuthError(413, "temporary_capacity", "Too many temporary attachments.")
        if self.worker.closing:
            raise AuthError(410, "temporary_expired", "This temporary chat has ended.")
        result = []
        with Session(self.engine) as db:
            for name, extension, size, parsed, data in prepared:
                identifier = f"tmp_{self.worker.identifier}_{uuid4().hex[:16]}"
                item = Attachment(
                    id=identifier,
                    owner_id=self.worker.owner,
                    display_name=name,
                    kind="image" if parsed["image"] else "document",
                    mime="image/webp" if parsed["image"] else MIMES[extension],
                    storage_name=identifier,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size=len(data),
                    original_size=size,
                    extracted_text=parsed["text"],
                    status=parsed["status"],
                    warnings_json=json.dumps(parsed["warnings"]),
                    width=parsed["width"],
                    height=parsed["height"],
                    created_at=self.now(),
                )
                db.add(item)
                result.append(self.info(item))
                self.blobs[identifier] = data
            db.commit()
        return result

    def remove(self, owner: str, identifier: str) -> None:
        with Session(self.engine) as db:
            item = self.get(db, owner, identifier)
            if db.scalar(
                select(RunAttachment.run_id).where(RunAttachment.attachment_id == identifier)
            ):
                raise AuthError(
                    409, "attachment_referenced", "This attachment belongs to a temporary answer."
                )
            db.delete(item)
            db.commit()
        self.blobs.pop(identifier, None)


class TemporaryRuns(RunService):
    def __init__(
        self, worker: "TemporaryWorker", main: RunService, assets: MemoryAttachments
    ) -> None:
        super().__init__(
            worker.engine, main.settings, main.provider, main.catalog, main.now, assets
        )
        self.main, self.worker = main, worker
        self.slots = main.slots
        self.admission: tuple[str, str] | None = None

    def estimate(self, model: ModelInfo, messages: list[dict[str, Any]], maximum: int) -> int:
        self.provider_budget = self.main.provider_budget
        return super().estimate(model, messages, maximum)

    async def authorize_dispatch(self) -> None:
        await self.main.authorize_dispatch()
        self.provider_budget = self.main.provider_budget
        if self.worker.closing:
            raise AuthError(410, "temporary_expired", "This temporary chat has ended.")

    def check_budget(
        self,
        db: Session,
        owner: str,
        reservation: int,
        simulated: bool,
        verification: bool,
        count: int = 1,
    ) -> None:
        # Admission and the durable content-free charge are atomic in create_queued.
        pass

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
        with Session(self.main.engine) as ledger:
            ledger.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if ledger.scalar(
                select(Charge.id).where(
                    Charge.owner_id == owner, Charge.idempotency_key == body.idempotency_key
                )
            ):
                raise AuthError(
                    410,
                    "temporary_replay",
                    "This submission was already accounted for. "
                    "Submit deliberately with a new key.",
                )
            self.main.check_budget(
                ledger, owner, reservation, model.simulated, body.verification_run
            )
            run = super().create_queued(
                db, owner, body, model, messages, prompt, turn_ids, reservation
            )
            charge = db.scalar(select(Charge).where(Charge.run_id == run.id))
            if charge is None:
                raise AuthError(500, "accounting_unavailable", "Usage accounting is unavailable.")
            ledger.add(
                Charge(
                    id=charge.id,
                    owner_id=owner,
                    idempotency_key=body.idempotency_key,
                    request_hash=digest(charge.id),
                    run_id=None,
                    state="reserved",
                    reserved_microusd=reservation,
                    actual_microusd=None,
                    purpose="temporary",
                    price_json=json.dumps({"model_id": model.id, "pricing": model.pricing}),
                    created_at=charge.created_at,
                )
            )
            ledger.commit()
            self.admission = charge.id, run.id
            return run

    async def start(self, owner: str, body: RunStart) -> RunInfo:
        if body.verification_run:
            raise AuthError(422, "invalid_request", "Verification runs require a saved chat.")
        if body.conversation_id != self.worker.identifier:
            raise AuthError(422, "invalid_conversation", "Choose this temporary chat.")
        with Session(self.engine) as db:
            existing = self.existing(db, owner, body.idempotency_key, body.request_hash())
            if existing:
                return existing
            runs = list(db.scalars(select(Run)))
            if (
                len(runs) >= 30
                or sum(len(r.prompt) + len(r.output) for r in runs) + len(body.prompt) > 250000
            ):
                raise AuthError(
                    413,
                    "temporary_capacity",
                    "This temporary chat has reached its memory limit. Start a new chat.",
                )
        self.admission = None
        try:
            return await super().start(owner, body)
        except Exception:
            if self.admission and self.admission[1] not in self.tasks:
                with Session(self.main.engine) as ledger:
                    charge = ledger.get(Charge, self.admission[0])
                    if charge and charge.state == "reserved":
                        charge.state, charge.actual_microusd = "settled", 0
                        ledger.commit()
            raise
        finally:
            self.admission = None

    def get(self, owner: str, run_id: str) -> RunInfo:
        with self.worker.lock:
            if self.worker.closing:
                raise AuthError(410, "temporary_expired", "This temporary chat has ended.")
            return super().get(owner, run_id)

    def cancel(self, owner: str, run_id: str) -> RunInfo:
        result = super().cancel(owner, run_id)
        self.mirror(run_id)
        return result

    async def stop(self) -> None:
        # The provider and execution slots are shared with regular chats.
        self.closing = True
        for identifier in list(self.tasks):
            self.cancel(self.worker.owner, identifier)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def mirror(self, run_id: str) -> None:
        with Session(self.engine) as db:
            charge = db.scalar(select(Charge).where(Charge.run_id == run_id))
            if not charge:
                return
            with Session(self.main.engine) as ledger:
                saved = ledger.get(Charge, charge.id)
                if saved:
                    saved.state, saved.actual_microusd = charge.state, charge.actual_microusd
                    details = json.loads(charge.price_json)
                    saved.price_json = json.dumps(
                        {
                            key: details[key]
                            for key in ("model_id", "pricing", "generation_id", "provider")
                            if key in details
                        }
                    )
                    ledger.commit()

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
        super().checkpoint(
            run_id, output, usage, provider, generation_id, first_token, elapsed, status, error
        )
        self.mirror(run_id)

    async def execute(self, run_id: str) -> None:
        try:
            await super().execute(run_id)
        finally:
            self.mirror(run_id)

    async def reconcile(self, owner: str, run_id: str) -> RunInfo:
        result = await super().reconcile(owner, run_id)
        self.mirror(run_id)
        return result


class TemporaryWorker:
    def __init__(self, main: RunService, owner: str, session_hash: str) -> None:
        self.identifier, self.owner, self.session_hash = uuid4().hex, owner, session_hash
        self.touched = main.now()
        self.closing = False
        self.operation = asyncio.Lock()
        lock = self.lock = threading.RLock()
        self.engine = create_engine(
            f"sqlite:///file:temporary-{self.identifier}?mode=memory&cache=shared&uri=true",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
            hide_parameters=True,
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection: Any, record: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA journal_mode=MEMORY")
            connection.execute("PRAGMA max_page_count=8192")

        @event.listens_for(self.engine, "begin")
        def acquire(connection: Any) -> None:
            lock.acquire()

        @event.listens_for(self.engine, "commit")
        @event.listens_for(self.engine, "rollback")
        def release(connection: Any) -> None:
            lock.release()

        # This anchor keeps the shared RAM database alive; no file or migration is created.
        self.anchor = self.engine.connect()
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add(Owner(id=owner, created_at=main.now()))
            db.flush()
            db.add(
                Conversation(
                    id=self.identifier,
                    owner_id=owner,
                    title="Temporary chat",
                    created_at=main.now(),
                    updated_at=main.now(),
                )
            )
            db.commit()
        self.assets = MemoryAttachments(self, main)
        self.runs = TemporaryRuns(self, main, self.assets)


class TemporaryChats:
    idle_seconds = 1800

    def __init__(self, main: RunService) -> None:
        self.main = main
        self.chats: dict[str, TemporaryWorker] = {}
        main.additional_active = lambda: sum(
            not task.done()
            for chat in list(self.chats.values())
            for task in list(chat.runs.tasks.values())
        )

    def create(self, session: OwnerSession) -> TemporaryWorker:
        if len(self.chats) >= 4:
            raise AuthError(
                429, "temporary_capacity", "Up to four temporary chats can be open. End one first."
            )
        worker = TemporaryWorker(self.main, session.owner_id, session.token_hash)
        self.chats[worker.identifier] = worker
        return worker

    def get(self, identifier: str, session: OwnerSession) -> TemporaryWorker:
        worker = self.chats.get(identifier)
        if (
            not worker
            or worker.closing
            or worker.owner != session.owner_id
            or worker.session_hash != session.token_hash
            or self.main.now() - worker.touched >= self.idle_seconds
        ):
            raise AuthError(
                410, "temporary_expired", "This temporary chat has ended and cannot be recovered."
            )
        worker.touched = self.main.now()
        return worker

    def attachment(self, identifier: str, session: OwnerSession) -> MemoryAttachments:
        parts = identifier.split("_")
        if len(parts) != 3:
            raise AuthError(404, "not_found", "Attachment not found.")
        return self.get(parts[1], session).assets

    async def close(self, worker: TemporaryWorker) -> None:
        worker.closing = True
        async with worker.operation:
            if worker.identifier not in self.chats:
                return
            await worker.runs.stop()
            worker.assets.blobs.clear()
            with worker.lock:
                worker.anchor.close()
                worker.engine.dispose()
            self.chats.pop(worker.identifier, None)

    async def sweep(self, all_chats: bool = False) -> None:
        for worker in list(self.chats.values()):
            with Session(self.main.engine) as db:
                session = db.get(OwnerSession, worker.session_hash)
                valid = session and self.main.now() < min(
                    session.expires_at, session.last_seen + self.main.settings.session_idle_seconds
                )
            if all_chats or not valid or self.main.now() - worker.touched >= self.idle_seconds:
                await self.close(worker)

    async def close_session(self, session_hash: str) -> None:
        for worker in list(self.chats.values()):
            if worker.session_hash == session_hash:
                await self.close(worker)

    def recover(self) -> None:
        with Session(self.main.engine) as db:
            db.execute(
                update(Charge)
                .where(Charge.purpose == "temporary", Charge.state == "reserved")
                .values(state="uncertain")
            )
            db.commit()
