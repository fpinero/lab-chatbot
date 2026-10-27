from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer)


class OwnerSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class AuthBucket(Base):
    __tablename__ = "auth_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index("ix_auth_buckets_window", "window_start"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    head_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer, index=True)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    comparison_id: Mapped[str | None] = mapped_column(
        ForeignKey("comparison_groups.id", ondelete="CASCADE"), nullable=True, index=True
    )
    model_id: Mapped[str] = mapped_column(String)
    turn: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(String)
    settings_json: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(String)
    output: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, index=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    generation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Charge(Base):
    __tablename__ = "usage_ledger"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    state: Mapped[str] = mapped_column(String, index=True)
    reserved_microusd: Mapped[int] = mapped_column(Integer)
    actual_microusd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String, default="generation", index=True)
    price_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer, index=True)
    __table_args__ = (Index("ux_ledger_owner_key", "owner_id", "idempotency_key", unique=True),)


class CatalogCache(Base):
    __tablename__ = "model_catalog_cache"
    family: Mapped[str] = mapped_column(String, primary_key=True)
    catalog_json: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[int] = mapped_column(Integer)
    last_attempt_at: Mapped[int] = mapped_column(Integer)


class Preferences(Base):
    __tablename__ = "preferences"
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("owners.id", ondelete="CASCADE"), primary_key=True
    )
    favorites_json: Mapped[str] = mapped_column(String, default="[]")


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String)
    mime: Mapped[str] = mapped_column(String)
    storage_name: Mapped[str] = mapped_column(String, unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    original_size: Mapped[int] = mapped_column(Integer)
    extracted_text: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    warnings_json: Mapped[str] = mapped_column(String)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, index=True)


class RunAttachment(Base):
    __tablename__ = "run_attachments"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    attachment_id: Mapped[str] = mapped_column(ForeignKey("attachments.id"), primary_key=True)


class Comparison(Base):
    __tablename__ = "comparison_groups"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index("ux_comparison_owner_key", "owner_id", "idempotency_key", unique=True),)


class MediaJob(Base):
    __tablename__ = "media_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("owners.id"), index=True)
    charge_id: Mapped[str] = mapped_column(ForeignKey("usage_ledger.id"), unique=True)
    family: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(String)
    request_json: Mapped[str] = mapped_column(String)
    settings_json: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    generation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, index=True)
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MediaJobAttachment(Base):
    __tablename__ = "media_job_attachments"
    job_id: Mapped[str] = mapped_column(
        ForeignKey("media_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    attachment_id: Mapped[str] = mapped_column(ForeignKey("attachments.id"), primary_key=True)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("media_jobs.id", ondelete="CASCADE"), index=True)
    storage_name: Mapped[str] = mapped_column(String, unique=True)
    mime: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
