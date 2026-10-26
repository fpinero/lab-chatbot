"""Add private attachments, immutable comparison groups and shared references."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("mime", sa.String(), nullable=False),
        sa.Column("storage_name", sa.String(), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("original_size", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("warnings_json", sa.String(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"])
    op.create_index("ix_attachments_created_at", "attachments", ["created_at"])
    op.create_table(
        "run_attachments",
        sa.Column(
            "run_id", sa.String(), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("attachment_id", sa.String(), sa.ForeignKey("attachments.id"), primary_key=True),
    )
    op.create_table(
        "comparison_groups",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ux_comparison_owner_key", "comparison_groups", ["owner_id", "idempotency_key"], unique=True
    )
    op.create_index("ix_comparison_groups_owner_id", "comparison_groups", ["owner_id"])
    op.create_index(
        "ix_comparison_groups_conversation_id", "comparison_groups", ["conversation_id"]
    )
    op.execute(
        "ALTER TABLE runs ADD COLUMN comparison_id VARCHAR "
        "REFERENCES comparison_groups(id) ON DELETE CASCADE"
    )
    op.create_index("ix_runs_comparison_id", "runs", ["comparison_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_comparison_id", "runs")
    op.execute("ALTER TABLE runs DROP COLUMN comparison_id")
    op.drop_table("comparison_groups")
    op.drop_table("run_attachments")
    op.drop_table("attachments")
