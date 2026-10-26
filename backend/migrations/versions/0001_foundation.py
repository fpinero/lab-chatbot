"""Create owner, hashed sessions and persistent authentication throttle."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "owner_id", sa.String(), sa.ForeignKey("owners.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_sessions_owner_id", "sessions", ["owner_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "auth_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_auth_buckets_window", "auth_buckets", ["window_start"])


def downgrade() -> None:
    op.drop_table("auth_buckets")
    op.drop_table("sessions")
    op.drop_table("owners")
