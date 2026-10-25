"""add trace and step names to llm_calls

Revision ID: 7c3e91a5d2b4
Revises: 4ec62d3af38f
Create Date: 2026-10-09 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c3e91a5d2b4"
down_revision: str | Sequence[str] | None = "4ec62d3af38f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("llm_calls", sa.Column("trace_name", sa.String(length=255), nullable=True))
    op.add_column("llm_calls", sa.Column("step_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("llm_calls", "step_name")
    op.drop_column("llm_calls", "trace_name")
