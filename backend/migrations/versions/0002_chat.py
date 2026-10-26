"""Persist conversations, immutable runs, catalog and transactional reservations."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("head_run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.String(), nullable=False),
        sa.Column("settings_json", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("output", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("generation_id", sa.String(), nullable=True),
        sa.Column("usage_json", sa.String(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.Integer(), nullable=True),
        sa.Column("first_token_ms", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
    )
    for column in ["owner_id", "conversation_id", "status"]:
        op.create_index(f"ix_runs_{column}", "runs", [column])
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("actual_microusd", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("price_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ux_ledger_owner_key", "usage_ledger", ["owner_id", "idempotency_key"], unique=True
    )
    for column in ["owner_id", "state", "created_at", "purpose"]:
        op.create_index(f"ix_usage_ledger_{column}", "usage_ledger", [column])
    op.create_table(
        "model_catalog_cache",
        sa.Column("family", sa.String(), primary_key=True),
        sa.Column("catalog_json", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "preferences",
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("favorites_json", sa.String(), nullable=False),
    )


def downgrade() -> None:
    for table in ["preferences", "model_catalog_cache", "usage_ledger", "runs", "conversations"]:
        op.drop_table(table)
