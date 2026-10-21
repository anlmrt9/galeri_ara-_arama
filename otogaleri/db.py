"""Veritabanı katmanı: şema (SQLAlchemy Core), engine fabrikası ve :class:`Repository`.

Şema değişiklikleri Alembic migration'larıyla yönetilir (``migrations/``);
:func:`init_db` uygulama açılışında ``alembic upgrade head`` çalıştırır.
PostgreSQL, SQL Server ve SQLite aynı kodla desteklenir — dialect'e özel SQL yoktur.

Tablolar:

* ``listings``       — ilanlar; ``(source_site, listing_id)`` benzersiz
* ``price_history``  — her fiyat gözlemi (fiyat düşüşü takibi)
* ``scan_jobs``      — tarama işleri kuyruğu (UI/API yazar, worker yürütür)
* ``site_runs``      — her turda her sitenin sonucu (kanal sağlığı)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from otogaleri.config import MSSQL_FROM_SETTINGS, Settings, get_settings
from otogaleri.damage import DamageReport
from otogaleri.models import Listing

log = logging.getLogger(__name__)

metadata = sa.MetaData()

listings = sa.Table(
    "listings",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("source_site", sa.Unicode(50), nullable=False),
    sa.Column("listing_id", sa.Unicode(100), nullable=False),
    sa.Column("brand", sa.Unicode(100), nullable=False, default=""),
    sa.Column("model", sa.Unicode(100), nullable=False, default=""),
    sa.Column("package_trim", sa.Unicode(200), nullable=False, default=""),
    sa.Column("year", sa.Integer, nullable=False, default=0),
    sa.Column("km", sa.Integer, nullable=False, default=0),
    sa.Column("price", sa.BigInteger, nullable=False, default=0),
    sa.Column("location", sa.Unicode(100), nullable=False, default=""),
    sa.Column("fuel", sa.Unicode(50), nullable=False, default=""),
    sa.Column("transmission", sa.Unicode(50), nullable=False, default=""),
    sa.Column("title", sa.Unicode(300), nullable=False, default=""),
    sa.Column("tramer_fee", sa.BigInteger, nullable=True),
    sa.Column("painted_parts", sa.UnicodeText, nullable=False, default=""),
    sa.Column("changed_parts", sa.UnicodeText, nullable=False, default=""),
    sa.Column("damage_json", sa.UnicodeText, nullable=True),
    sa.Column("link", sa.Unicode(1000), nullable=False),
    sa.Column("first_seen_at", sa.DateTime, nullable=False),
    sa.Column("last_seen_at", sa.DateTime, nullable=False),
    sa.Column("price_changed_at", sa.DateTime, nullable=True),
    sa.Column("initial_price", sa.BigInteger, nullable=False, default=0),
    sa.Column("is_new_listing", sa.Boolean, nullable=False, default=True),
    sa.UniqueConstraint("source_site", "listing_id", name="uq_listings_site_listing"),
)
sa.Index("ix_listings_first_seen_at", listings.c.first_seen_at)
sa.Index("ix_listings_brand_model_year", listings.c.brand, listings.c.model, listings.c.year)

price_history = sa.Table(
    "price_history",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column(
        "listing_pk", sa.Integer, sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    ),
    sa.Column("price", sa.BigInteger, nullable=False),
    sa.Column("observed_at", sa.DateTime, nullable=False),
)
sa.Index("ix_price_history_listing_pk", price_history.c.listing_pk)

scan_jobs = sa.Table(
    "scan_jobs",
    metadata,
    sa.Column("id", sa.Unicode(36), primary_key=True),
    sa.Column("criteria_json", sa.UnicodeText, nullable=False),
    sa.Column("status", sa.Unicode(20), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("ends_at", sa.DateTime, nullable=False),
    sa.Column("started_at", sa.DateTime, nullable=True),
    sa.Column("finished_at", sa.DateTime, nullable=True),
    sa.Column("worker_id", sa.Unicode(100), nullable=True),
    sa.Column("heartbeat_at", sa.DateTime, nullable=True),
    sa.Column("cycles", sa.Integer, nullable=False, default=0),
    sa.Column("last_cycle_at", sa.DateTime, nullable=True),
    sa.Column("next_cycle_at", sa.DateTime, nullable=True),
    sa.Column("error", sa.UnicodeText, nullable=True),
    # tur sonu sayaçları (migration 0003)
    sa.Column("last_cycle_seen", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_cycle_matched", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_cycle_new", sa.Integer, nullable=False, server_default="0"),
    sa.Column("found_total", sa.Integer, nullable=False, server_default="0"),
)
sa.Index("ix_scan_jobs_status", scan_jobs.c.status)

site_runs = sa.Table(
    "site_runs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("job_id", sa.Unicode(36), nullable=False),
    sa.Column("site", sa.Unicode(50), nullable=False),
    sa.Column("started_at", sa.DateTime, nullable=False),
    sa.Column("finished_at", sa.DateTime, nullable=False),
    sa.Column("status", sa.Unicode(20), nullable=False),
    sa.Column("seen", sa.Integer, nullable=False, default=0),
    sa.Column("matched", sa.Integer, nullable=False, default=0),
    sa.Column("new", sa.Integer, nullable=False, default=0),
    sa.Column("price_drops", sa.Integer, nullable=False, default=0),
    sa.Column("error", sa.UnicodeText, nullable=True),
)
sa.Index("ix_site_runs_site_finished", site_runs.c.site, site_runs.c.finished_at)

JobStatus = Literal["pending", "running", "stop_requested", "stopped", "completed", "failed"]
ACTIVE_STATUSES: tuple[str, ...] = ("pending", "running", "stop_requested")


def utcnow() -> datetime:
    """Veritabanına yazılan tüm zamanlar: saat dilimsiz UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================================================================
#  ENGINE
# ==========================================================================

_DB_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _detect_odbc_driver() -> str:
    try:
        import pyodbc

        drivers = sorted(
            d for d in pyodbc.drivers() if re.match(r"ODBC Driver \d+ for SQL Server", d)
        )
        if drivers:
            return str(drivers[-1])
    except Exception:
        log.debug("ODBC surucu listesi alinamadi", exc_info=True)
    return "ODBC Driver 17 for SQL Server"


def _ensure_mssql_database(settings: Settings, driver: str) -> None:
    """SQL Server'da hedef veritabanı yoksa oluşturur (adı doğrulanır, parametreli sorgu)."""
    if not _DB_NAME_RE.match(settings.db_name):
        raise ValueError(f"Gecersiz veritabani adi: {settings.db_name!r}")
    import pyodbc

    conn = pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={settings.db_server};DATABASE=master;"
        "Trusted_Connection=yes;TrustServerCertificate=yes",
        autocommit=True,
        timeout=settings.db_connect_timeout,
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM sys.databases WHERE name = ?", settings.db_name)
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE [{settings.db_name}]")
            log.info("%s veritabani olusturuldu.", settings.db_name)
    finally:
        conn.close()


def create_db_engine(settings: Settings | None = None, url: str | None = None) -> Engine:
    """Ayarlara göre engine kurar ve bağlantıyı doğrular (başarısızsa istisna yükseltir)."""
    settings = settings or get_settings()
    url = url or settings.resolved_database_url()

    if url.startswith("mssql"):
        if url == MSSQL_FROM_SETTINGS:  # OTOGALERI_DB_SERVER / DB_NAME ile Windows Authentication
            driver = settings.odbc_driver or _detect_odbc_driver()
            _ensure_mssql_database(settings, driver)
            url = (
                f"mssql+pyodbc://@{settings.db_server}/{settings.db_name}"
                f"?driver={quote_plus(driver)}&Trusted_Connection=yes&TrustServerCertificate=yes"
            )
        engine = sa.create_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_recycle_seconds,
            pool_pre_ping=True,
            connect_args={"timeout": settings.db_connect_timeout},
        )
    elif url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = sa.create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @sa.event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    else:
        engine = sa.create_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_recycle_seconds,
            pool_pre_ping=True,
        )

    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1"))
    log.info("[DB] Baglanti basarili (%s).", engine.dialect.name)
    return engine


def init_db(engine: Engine) -> None:
    """Şemayı en güncel migration'a yükseltir (``alembic upgrade head``)."""
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


# ==========================================================================
#  REPOSITORY
# ==========================================================================


@dataclass(frozen=True)
class UpsertResult:
    kind: Literal["new", "price_drop", "price_rise", "unchanged"]
    pk: int
    old_price: int | None = None


class Repository:
    """Tüm okuma/yazma işlemleri. Thread-safe'tir (her çağrı kendi bağlantısını alır)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ---------- İLANLAR ----------

    def known_ids(self, site: str, listing_ids: list[str]) -> set[str]:
        if not listing_ids:
            return set()
        found: set[str] = set()
        with self.engine.connect() as conn:
            for i in range(0, len(listing_ids), 500):  # SQL Server parametre sınırı
                chunk = listing_ids[i : i + 500]
                rows = conn.execute(
                    sa.select(listings.c.listing_id).where(
                        listings.c.source_site == site, listings.c.listing_id.in_(chunk)
                    )
                )
                found.update(r[0] for r in rows)
        return found

    def upsert_listing(self, item: Listing) -> UpsertResult:
        """Yeni ilanı ekler; bilineni ``last_seen_at``/fiyat açısından günceller.

        Hasar alanları yalnızca ``item.damage`` doluysa yazılır (liste özeti mevcut
        detay bilgisinin üzerine yazmaz). Eşzamanlı ekleme yarışında
        ``IntegrityError`` yakalanır ve güncellemeye dönülür.
        """
        now = utcnow()
        try:
            with self.engine.begin() as conn:
                row = self._find(conn, item)
                if row is None:
                    pk = self._insert(conn, item, now)
                    return UpsertResult("new", pk)
                return self._update(conn, row, item, now)
        except IntegrityError:
            with self.engine.begin() as conn:
                row = self._find(conn, item)
                if row is None:
                    raise
                return self._update(conn, row, item, now)

    @staticmethod
    def _find(conn: sa.Connection, item: Listing) -> sa.Row[Any] | None:
        return conn.execute(
            sa.select(listings.c.id, listings.c.price).where(
                listings.c.source_site == item.source_site,
                listings.c.listing_id == item.listing_id,
            )
        ).first()

    @staticmethod
    def _insert(conn: sa.Connection, item: Listing, now: datetime) -> int:
        values = {
            "source_site": item.source_site,
            "listing_id": item.listing_id,
            "brand": item.brand[:100],
            "model": item.model[:100],
            "package_trim": item.trim[:200],
            "year": item.year,
            "km": item.km,
            "price": item.price,
            "initial_price": item.price,
            "location": item.location[:100],
            "fuel": item.fuel[:50],
            "transmission": item.transmission[:50],
            "title": item.title[:300],
            "tramer_fee": item.tramer,
            "damage_json": json.dumps(item.damage.to_dict()) if item.damage else None,
            "link": item.link[:1000],
            "first_seen_at": now,
            "last_seen_at": now,
            "is_new_listing": True,
            **item.damage_columns(),
        }
        result = conn.execute(listings.insert().values(**values))
        pk = int(result.inserted_primary_key[0])  # type: ignore[index]
        conn.execute(
            price_history.insert().values(listing_pk=pk, price=item.price, observed_at=now)
        )
        return pk

    @staticmethod
    def _update(
        conn: sa.Connection, row: sa.Row[Any], item: Listing, now: datetime
    ) -> UpsertResult:
        pk, old_price = int(row.id), int(row.price)
        values: dict[str, Any] = {"last_seen_at": now}
        if item.damage is not None:
            values.update(
                tramer_fee=item.tramer,
                damage_json=json.dumps(item.damage.to_dict()),
                **item.damage_columns(),
            )
        kind: Literal["price_drop", "price_rise", "unchanged"] = "unchanged"
        if item.price and item.price != old_price:
            kind = "price_drop" if item.price < old_price else "price_rise"
            values.update(price=item.price, price_changed_at=now)
            conn.execute(
                price_history.insert().values(listing_pk=pk, price=item.price, observed_at=now)
            )
        conn.execute(listings.update().where(listings.c.id == pk).values(**values))
        return UpsertResult(kind, pk, old_price)

    def list_listings(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        site: str | None = None,
        only_new: bool = False,
    ) -> list[dict[str, Any]]:
        q = sa.select(listings).order_by(listings.c.first_seen_at.desc(), listings.c.id.desc())
        if site:
            q = q.where(listings.c.source_site == site)
        if only_new:
            q = q.where(listings.c.is_new_listing == sa.true())
        if limit is not None:
            q = q.limit(limit).offset(offset)
        elif offset:
            q = q.offset(offset)
        with self.engine.connect() as conn:
            return [_listing_row(r._mapping) for r in conn.execute(q)]

    def count_listings(self, *, site: str | None = None, only_new: bool = False) -> int:
        q = sa.select(sa.func.count()).select_from(listings)
        if site:
            q = q.where(listings.c.source_site == site)
        if only_new:
            q = q.where(listings.c.is_new_listing == sa.true())
        with self.engine.connect() as conn:
            return int(conn.execute(q).scalar_one())

    def get_price_history(self, pk: int) -> list[dict[str, Any]]:
        q = (
            sa.select(price_history.c.price, price_history.c.observed_at)
            .where(price_history.c.listing_pk == pk)
            .order_by(price_history.c.observed_at)
        )
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    def mark_all_seen(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                listings.update()
                .where(listings.c.is_new_listing == sa.true())
                .values(is_new_listing=False)
            )

    def clear_listings(self) -> int:
        with self.engine.begin() as conn:
            conn.execute(price_history.delete())
            return int(conn.execute(listings.delete()).rowcount or 0)

    # ---------- TARAMA İŞLERİ ----------

    def create_job(self, job_id: str, criteria_json: str, ends_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                scan_jobs.insert().values(
                    id=job_id,
                    criteria_json=criteria_json,
                    status="pending",
                    created_at=utcnow(),
                    ends_at=ends_at,
                    cycles=0,
                )
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(scan_jobs).where(scan_jobs.c.id == job_id)).first()
        return dict(row._mapping) if row else None

    def active_job(self) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(scan_jobs)
                .where(scan_jobs.c.status.in_(ACTIVE_STATUSES))
                .order_by(scan_jobs.c.created_at.desc())
            ).first()
        return dict(row._mapping) if row else None

    def latest_job(self) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(scan_jobs).order_by(scan_jobs.c.created_at.desc())).first()
        return dict(row._mapping) if row else None

    def claim_job(self, worker_id: str, stale_after: timedelta) -> dict[str, Any] | None:
        """Bekleyen ya da sahibi ölmüş (heartbeat'i eskimiş) bir işi atomik olarak üstlenir."""
        now = utcnow()
        stale_before = now - stale_after
        with self.engine.connect() as conn:
            candidates = conn.execute(
                sa.select(scan_jobs.c.id)
                .where(scan_jobs.c.status.in_(("pending", "running", "stop_requested")))
                .order_by(scan_jobs.c.created_at)
            ).all()
        for (job_id,) in candidates:
            with self.engine.begin() as conn:
                result = conn.execute(
                    scan_jobs.update()
                    .where(
                        scan_jobs.c.id == job_id,
                        sa.or_(
                            scan_jobs.c.status == "pending",
                            sa.and_(
                                scan_jobs.c.status.in_(("running", "stop_requested")),
                                sa.or_(
                                    scan_jobs.c.heartbeat_at.is_(None),
                                    scan_jobs.c.heartbeat_at < stale_before,
                                ),
                            ),
                        ),
                    )
                    .values(
                        status=sa.case(
                            (scan_jobs.c.status == "stop_requested", "stop_requested"),
                            else_="running",
                        ),
                        worker_id=worker_id,
                        heartbeat_at=now,
                        started_at=sa.func.coalesce(scan_jobs.c.started_at, now),
                    )
                )
                claimed = result.rowcount == 1
            if claimed:  # commit'ten sonra oku
                return self.get_job(job_id)
        return None

    def heartbeat(self, job_id: str, worker_id: str, **fields: Any) -> str | None:
        """Kalp atışı yazar ve işin güncel durumunu döndürür (sahiplik kaybedildiyse ``None``)."""
        with self.engine.begin() as conn:
            result = conn.execute(
                scan_jobs.update()
                .where(scan_jobs.c.id == job_id, scan_jobs.c.worker_id == worker_id)
                .values(heartbeat_at=utcnow(), **fields)
            )
            if result.rowcount != 1:
                return None
            return str(
                conn.execute(
                    sa.select(scan_jobs.c.status).where(scan_jobs.c.id == job_id)
                ).scalar_one()
            )

    def request_stop(self, job_id: str, stale_after: timedelta) -> bool:
        """Durdurma ister. Henüz başlamamış ya da sahipsiz iş doğrudan ``stopped`` olur."""
        job = self.get_job(job_id)
        if not job or job["status"] not in ACTIVE_STATUSES:
            return False
        hb = job.get("heartbeat_at")
        orphan = job["status"] == "pending" or hb is None or hb < utcnow() - stale_after
        with self.engine.begin() as conn:
            conn.execute(
                scan_jobs.update()
                .where(scan_jobs.c.id == job_id)
                .values(
                    status="stopped" if orphan else "stop_requested",
                    finished_at=utcnow() if orphan else None,
                )
            )
        return True

    def finish_job(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                scan_jobs.update()
                .where(scan_jobs.c.id == job_id)
                .values(status=status, finished_at=utcnow(), error=error, next_cycle_at=None)
            )

    # ---------- SİTE ÇALIŞMALARI ----------

    def record_site_run(self, **values: Any) -> None:
        with self.engine.begin() as conn:
            conn.execute(site_runs.insert().values(**values))

    def latest_site_runs(self) -> dict[str, dict[str, Any]]:
        """Her sitenin en son çalışması (UI'daki kanal sağlığı göstergesi)."""
        latest = (
            sa.select(site_runs.c.site, sa.func.max(site_runs.c.id).label("max_id"))
            .group_by(site_runs.c.site)
            .subquery()
        )
        q = sa.select(site_runs).join(latest, site_runs.c.id == latest.c.max_id)
        with self.engine.connect() as conn:
            return {r.site: dict(r._mapping) for r in conn.execute(q)}

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - sağlık kontrolü: her hata "erişilemiyor" demek
            return False


def _listing_row(m: Any) -> dict[str, Any]:
    row = dict(m)
    row["is_new_listing"] = bool(row.get("is_new_listing"))
    report = (
        DamageReport.from_dict(json.loads(row["damage_json"])) if row.get("damage_json") else None
    )
    row.pop("damage_json", None)
    row["damage"] = report.to_dict() if report else None
    row["scraped_at"] = row.get("first_seen_at")  # geriye uyumluluk (mobil uygulama)
    return row
