"""Eski sürümün ``Cars`` tablosundaki ilanları ``listings``'e aktarır (varsa).

``Cars`` tablosuna dokunulmaz; doğrulama sonrası elle silinebilir. Eski şemada
``listing_id`` siteler arası benzersizdi, yeni şemada ``(source_site, listing_id)``.

Revision ID: 0002_import_legacy_cars
Revises: 0001_initial
Create Date: 2026-10-21
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0002_import_legacy_cars"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "source_site",
    "listing_id",
    "brand",
    "model",
    "package_trim",
    "year",
    "km",
    "price",
    "initial_price",
    "location",
    "fuel",
    "transmission",
    "title",
    "tramer_fee",
    "painted_parts",
    "changed_parts",
    "link",
    "first_seen_at",
    "last_seen_at",
    "is_new_listing",
)


def _text(value: object, limit: int) -> str:
    return ("" if value is None else str(value))[:limit]


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


def _when(value: object, default: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return default


def upgrade() -> None:
    bind = op.get_bind()
    legacy_name = next((t for t in sa.inspect(bind).get_table_names() if t.lower() == "cars"), None)
    if legacy_name is None:
        return
    legacy = sa.Table(legacy_name, sa.MetaData(), autoload_with=bind)
    listings = sa.table("listings", *(sa.column(c) for c in _COLUMNS))
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    seen: set[tuple[str, str]] = set()
    rows = []
    for r in bind.execute(sa.select(legacy)).mappings():
        site = _text(r.get("source_site"), 50) or "Bilinmiyor"
        lid = _text(r.get("listing_id"), 100)
        if not lid or (site, lid) in seen:
            continue
        seen.add((site, lid))
        when = _when(r.get("scraped_at"), now)
        price = _int(r.get("price"))
        rows.append(
            {
                "source_site": site,
                "listing_id": lid,
                "brand": _text(r.get("brand"), 100),
                "model": _text(r.get("model"), 100),
                "package_trim": _text(r.get("package_trim"), 200),
                "year": _int(r.get("year")),
                "km": _int(r.get("km")),
                "price": price,
                "initial_price": price,
                "location": _text(r.get("location"), 100),
                "fuel": "",
                "transmission": "",
                "title": "",
                "tramer_fee": _int(r.get("tramer_fee")) or None,
                "painted_parts": _text(r.get("painted_parts"), 4000),
                "changed_parts": _text(r.get("changed_parts"), 4000),
                "link": _text(r.get("link"), 1000),
                "first_seen_at": when,
                "last_seen_at": when,
                "is_new_listing": False,
            }
        )
    if rows:
        op.bulk_insert(listings, rows)


def downgrade() -> None:
    # Aktarılan satırlar ayırt edilemediği için geri alma veri silmez.
    pass
