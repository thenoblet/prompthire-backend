"""cache and rate limit hardening v2

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_cache",
        sa.Column("role_hash", sa.Text, primary_key=True),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("normalized_role", sa.Text, nullable=False),
        sa.Column("response", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_question_cache_expires_at",
        "question_cache",
        ["expires_at"],
    )

    op.create_table(
        "rate_limit_daily",
        sa.Column("ip", sa.Text, primary_key=True),
        sa.Column("route", sa.Text, primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
    )

    op.create_table(
        "global_daily_count",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("route", sa.Text, primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
    )

    op.drop_constraint(
        "status_in_allowed",
        "generations",
        type_="check",
    )
    op.create_check_constraint(
        "status_in_allowed",
        "generations",
        "status IN ('ok', 'bad_shape', 'upstream_err', 'cache_hit')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "status_in_allowed",
        "generations",
        type_="check",
    )
    op.create_check_constraint(
        "status_in_allowed",
        "generations",
        "status IN ('ok', 'bad_shape', 'upstream_err')",
    )

    op.drop_table("global_daily_count")
    op.drop_table("rate_limit_daily")
    op.drop_index("ix_question_cache_expires_at", table_name="question_cache")
    op.drop_table("question_cache")
