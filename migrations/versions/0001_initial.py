"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("questions", JSONB, nullable=True),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'bad_shape', 'upstream_err')",
            name="status_in_allowed",
        ),
    )
    op.create_index(
        "ix_generations_created_at",
        "generations",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_generations_status_created_at",
        "generations",
        ["status", sa.text("created_at DESC")],
    )

    op.create_table(
        "rate_limit_buckets",
        sa.Column("ip", sa.Text, primary_key=True),
        sa.Column("route", sa.Text, primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
    )
    op.create_index(
        "ix_rate_limit_buckets_window_start",
        "rate_limit_buckets",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_buckets_window_start", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_generations_status_created_at", table_name="generations")
    op.drop_index("ix_generations_created_at", table_name="generations")
    op.drop_table("generations")
