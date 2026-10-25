"""add project slug

A project now has a slug: the short, URL-safe identifier that the SDK, the addresses and the S3
keys use, while the name is only a label. Existing projects get the slug of their name (the same
rules as ``app/slugs.py``, copied here so the migration never changes when the code does), with
``-2``, ``-3``... added when two names give the same slug.

Downgrading drops the column.

Revision ID: d41f7a2c9b60
Revises: b5d8a3c1e7f2
Create Date: 2026-10-09 15:00:00.000000

"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d41f7a2c9b60"
down_revision: str | Sequence[str] | None = "b5d8a3c1e7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_SLUG_LENGTH = 64


def _slugify(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")[:MAX_SLUG_LENGTH].strip("-")
    return slug or "project"


def _next_free(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    number = 2
    while True:
        suffix = f"-{number}"
        candidate = base[: MAX_SLUG_LENGTH - len(suffix)].rstrip("-") + suffix
        if candidate not in taken:
            return candidate
        number += 1


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("projects", sa.Column("slug", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    taken: set[str] = set()
    for project_id, name in bind.execute(sa.text("SELECT id, name FROM projects ORDER BY id")):
        slug = _next_free(_slugify(name), taken)
        taken.add(slug)
        bind.execute(
            sa.text("UPDATE projects SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": project_id},
        )

    op.alter_column("projects", "slug", nullable=False)
    op.create_unique_constraint(None, "projects", ["slug"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("projects_slug_key", "projects", type_="unique")
    op.drop_column("projects", "slug")
