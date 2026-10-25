"""add projects

Every volume now belongs to a project, and a volume name is unique within its project instead of
globally. Existing volumes (and their calls) move into a project called ``default``. The
``app_name`` column of ``llm_calls`` is dropped: the project replaces it.

Downgrading re-adds ``app_name`` empty (the old values are not recoverable) and restores global
volume-name uniqueness, so it refuses to run while a volume name exists in several projects.

Revision ID: b5d8a3c1e7f2
Revises: 7c3e91a5d2b4
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d8a3c1e7f2"
down_revision: str | Sequence[str] | None = "7c3e91a5d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.execute("INSERT INTO projects (name) VALUES ('default')")

    op.add_column("volumes", sa.Column("project_id", sa.BigInteger(), nullable=True))
    op.execute("UPDATE volumes SET project_id = (SELECT id FROM projects WHERE name = 'default')")
    op.alter_column("volumes", "project_id", nullable=False)
    op.create_foreign_key(
        "volumes_project_id_fkey", "volumes", "projects", ["project_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_constraint("volumes_name_key", "volumes", type_="unique")
    op.create_unique_constraint("uq_volumes_project_name", "volumes", ["project_id", "name"])

    op.drop_column("llm_calls", "app_name")


def downgrade() -> None:
    """Downgrade schema."""
    shared = (
        op.get_bind()
        .execute(sa.text("SELECT name FROM volumes GROUP BY name HAVING count(*) > 1 LIMIT 5"))
        .scalars()
        .all()
    )
    if shared:
        raise RuntimeError(
            f"Cannot downgrade: these volume names exist in several projects: {shared}. "
            "Rename or delete the duplicates first."
        )

    op.add_column("llm_calls", sa.Column("app_name", sa.String(length=255), nullable=True))

    op.drop_constraint("uq_volumes_project_name", "volumes", type_="unique")
    op.create_unique_constraint("volumes_name_key", "volumes", ["name"])
    op.drop_constraint("volumes_project_id_fkey", "volumes", type_="foreignkey")
    op.drop_column("volumes", "project_id")

    op.drop_table("projects")
