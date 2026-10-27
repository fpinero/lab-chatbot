"""Add durable media jobs and private generated assets without rebuilding accounting."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column(
            "charge_id", sa.String(), sa.ForeignKey("usage_ledger.id"), nullable=False, unique=True
        ),
        sa.Column("family", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("request_json", sa.String(), nullable=False),
        sa.Column("settings_json", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("generation_id", sa.String(), nullable=True),
        sa.Column("usage_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Integer(), nullable=True),
    )
    for column in ["owner_id", "status", "created_at"]:
        op.create_index(f"ix_media_jobs_{column}", "media_jobs", [column])
    op.create_table(
        "media_job_attachments",
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("media_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attachment_id", sa.String(), sa.ForeignKey("attachments.id"), primary_key=True),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("media_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_name", sa.String(), nullable=False, unique=True),
        sa.Column("mime", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_media_assets_job_id", "media_assets", ["job_id"])
    op.create_index("ix_media_assets_expires_at", "media_assets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("media_assets")
    op.drop_table("media_job_attachments")
    op.drop_table("media_jobs")
