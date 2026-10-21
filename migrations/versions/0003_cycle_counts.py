"""scan_jobs: tur sonu sayaçları (son turda taranan / uyan / yeni, iş boyunca bulunan).

Revision ID: 0003_cycle_counts
Revises: 0002_import_legacy_cars
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_cycle_counts"
down_revision: str | None = "0002_import_legacy_cars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("last_cycle_seen", "last_cycle_matched", "last_cycle_new", "found_total")


def upgrade() -> None:
    with op.batch_alter_table("scan_jobs") as batch:
        for name in _COLUMNS:
            batch.add_column(sa.Column(name, sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("scan_jobs") as batch:
        for name in reversed(_COLUMNS):
            batch.drop_column(name)
