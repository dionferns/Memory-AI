"""sources folder filename uniqueness

Revision ID: d67a7ef2d7a4
Revises: 03761d5ed341
Create Date: 2026-07-18 12:19:25.667396

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d67a7ef2d7a4"
down_revision: str | Sequence[str] | None = "03761d5ed341"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Ticket 05 decision #10: per-folder filename uniqueness is
    case-insensitive and enforced at the DB level -- a functional unique
    index on `(folder_id, lower(filename))`, not just an application-code
    check.
    """
    op.create_index(
        "ix_sources_folder_id_lower_filename",
        "sources",
        ["folder_id", sa.text("lower(filename)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sources_folder_id_lower_filename", table_name="sources")
