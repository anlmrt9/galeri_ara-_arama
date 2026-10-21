"""İlk şema: listings, price_history, scan_jobs, site_runs.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_site", sa.Unicode(50), nullable=False),
        sa.Column("listing_id", sa.Unicode(100), nullable=False),
        sa.Column("brand", sa.Unicode(100), nullable=False),
        sa.Column("model", sa.Unicode(100), nullable=False),
        sa.Column("package_trim", sa.Unicode(200), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("km", sa.Integer, nullable=False),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("location", sa.Unicode(100), nullable=False),
        sa.Column("fuel", sa.Unicode(50), nullable=False),
        sa.Column("transmission", sa.Unicode(50), nullable=False),
        sa.Column("title", sa.Unicode(300), nullable=False),
        sa.Column("tramer_fee", sa.BigInteger, nullable=True),
        sa.Column("painted_parts", sa.UnicodeText, nullable=False),
        sa.Column("changed_parts", sa.UnicodeText, nullable=False),
        sa.Column("damage_json", sa.UnicodeText, nullable=True),
        sa.Column("link", sa.Unicode(1000), nullable=False),
        sa.Column("first_seen_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("price_changed_at", sa.DateTime, nullable=True),
        sa.Column("initial_price", sa.BigInteger, nullable=False),
        sa.Column("is_new_listing", sa.Boolean, nullable=False),
        sa.UniqueConstraint("source_site", "listing_id", name="uq_listings_site_listing"),
    )
    op.create_index("ix_listings_first_seen_at", "listings", ["first_seen_at"])
    op.create_index("ix_listings_brand_model_year", "listings", ["brand", "model", "year"])

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "listing_pk",
            sa.Integer,
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("observed_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_price_history_listing_pk", "price_history", ["listing_pk"])

    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Unicode(36), primary_key=True),
        sa.Column("criteria_json", sa.UnicodeText, nullable=False),
        sa.Column("status", sa.Unicode(20), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("ends_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("worker_id", sa.Unicode(100), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime, nullable=True),
        sa.Column("cycles", sa.Integer, nullable=False),
        sa.Column("last_cycle_at", sa.DateTime, nullable=True),
        sa.Column("next_cycle_at", sa.DateTime, nullable=True),
        sa.Column("error", sa.UnicodeText, nullable=True),
    )
    op.create_index("ix_scan_jobs_status", "scan_jobs", ["status"])

    op.create_table(
        "site_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Unicode(36), nullable=False),
        sa.Column("site", sa.Unicode(50), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.Unicode(20), nullable=False),
        sa.Column("seen", sa.Integer, nullable=False),
        sa.Column("matched", sa.Integer, nullable=False),
        sa.Column("new", sa.Integer, nullable=False),
        sa.Column("price_drops", sa.Integer, nullable=False),
        sa.Column("error", sa.UnicodeText, nullable=True),
    )
    op.create_index("ix_site_runs_site_finished", "site_runs", ["site", "finished_at"])


def downgrade() -> None:
    op.drop_table("site_runs")
    op.drop_table("scan_jobs")
    op.drop_table("price_history")
    op.drop_table("listings")
