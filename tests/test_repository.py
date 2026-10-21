from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from otogaleri.damage import DamageReport, DamageState
from otogaleri.db import Repository, create_db_engine, init_db, utcnow
from otogaleri.models import Listing


def _listing(lid: str = "OP-1", price: int = 1_000_000, site: str = "Otoplus", **kw) -> Listing:
    return Listing(
        site,
        lid,
        f"https://example.com/{lid}",
        brand="Fiat",
        model="Egea",
        year=2020,
        km=50_000,
        price=price,
        **kw,
    )


class TestUpsert:
    def test_new_then_unchanged(self, repo: Repository):
        assert repo.upsert_listing(_listing()).kind == "new"
        assert repo.upsert_listing(_listing()).kind == "unchanged"
        assert repo.count_listings() == 1

    def test_same_id_on_different_sites_are_distinct(self, repo: Repository):
        repo.upsert_listing(_listing("123", site="Otoplus"))
        repo.upsert_listing(_listing("123", site="Arabam.com"))
        assert repo.count_listings() == 2

    def test_price_drop_is_recorded_in_history(self, repo: Repository):
        pk = repo.upsert_listing(_listing(price=1_000_000)).pk
        result = repo.upsert_listing(_listing(price=950_000))
        assert (result.kind, result.old_price) == ("price_drop", 1_000_000)
        assert [h["price"] for h in repo.get_price_history(pk)] == [1_000_000, 950_000]
        row = repo.list_listings()[0]
        assert row["price"] == 950_000 and row["initial_price"] == 1_000_000
        assert row["price_changed_at"] is not None

    def test_price_rise(self, repo: Repository):
        repo.upsert_listing(_listing(price=100))
        assert repo.upsert_listing(_listing(price=120)).kind == "price_rise"

    def test_summary_without_damage_keeps_existing_damage(self, repo: Repository):
        report = DamageReport.all_original(tramer=500)
        report.parts["kaput"] = DamageState.PAINTED
        repo.upsert_listing(_listing(damage=report))
        repo.upsert_listing(_listing())  # liste özeti: damage=None
        row = repo.list_listings()[0]
        assert row["painted_parts"] == "Kaput"
        assert row["tramer_fee"] == 500
        assert row["damage"]["parts"]["kaput"] == "painted"

    def test_known_ids(self, repo: Repository):
        repo.upsert_listing(_listing("A"))
        repo.upsert_listing(_listing("B"))
        assert repo.known_ids("Otoplus", ["A", "C"]) == {"A"}
        assert repo.known_ids("Otoplus", []) == set()

    def test_mark_all_seen_and_clear(self, repo: Repository):
        repo.upsert_listing(_listing("A"))
        assert repo.count_listings(only_new=True) == 1
        repo.mark_all_seen()
        assert repo.count_listings(only_new=True) == 0
        assert repo.clear_listings() == 1
        assert repo.count_listings() == 0

    def test_pagination_and_site_filter(self, repo: Repository):
        for i in range(5):
            repo.upsert_listing(_listing(f"OP-{i}"))
        repo.upsert_listing(_listing("X", site="Arabam.com"))
        assert len(repo.list_listings(limit=2)) == 2
        assert len(repo.list_listings(limit=10, offset=4)) == 2
        assert {r["source_site"] for r in repo.list_listings(site="Arabam.com")} == {"Arabam.com"}


class TestJobs:
    STALE = timedelta(seconds=60)

    def test_claim_pending_job_once(self, repo: Repository):
        repo.create_job("j1", "{}", utcnow() + timedelta(hours=1))
        job = repo.claim_job("w1", self.STALE)
        assert job and job["status"] == "running" and job["worker_id"] == "w1"
        assert repo.claim_job("w2", self.STALE) is None  # canlı sahibi var

    def test_stale_job_is_taken_over(self, repo: Repository):
        repo.create_job("j1", "{}", utcnow() + timedelta(hours=1))
        repo.claim_job("w1", self.STALE)
        with repo.engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE scan_jobs SET heartbeat_at = :t"),
                {"t": utcnow() - timedelta(minutes=5)},
            )
        job = repo.claim_job("w2", self.STALE)
        assert job and job["worker_id"] == "w2"

    def test_heartbeat_requires_ownership(self, repo: Repository):
        repo.create_job("j1", "{}", utcnow() + timedelta(hours=1))
        repo.claim_job("w1", self.STALE)
        assert repo.heartbeat("j1", "w1") == "running"
        assert repo.heartbeat("j1", "intruder") is None

    def test_stop_pending_job_is_immediate(self, repo: Repository):
        repo.create_job("j1", "{}", utcnow() + timedelta(hours=1))
        assert repo.request_stop("j1", self.STALE)
        assert repo.get_job("j1")["status"] == "stopped"  # type: ignore[index]
        assert repo.active_job() is None

    def test_stop_running_job_is_requested(self, repo: Repository):
        repo.create_job("j1", "{}", utcnow() + timedelta(hours=1))
        repo.claim_job("w1", self.STALE)
        repo.request_stop("j1", self.STALE)
        assert repo.heartbeat("j1", "w1") == "stop_requested"

    def test_latest_site_runs(self, repo: Repository):
        now = utcnow()
        for status in ("failed", "ok"):
            repo.record_site_run(
                job_id="j",
                site="Otoplus",
                started_at=now,
                finished_at=now,
                status=status,
                seen=1,
                matched=1,
                new=0,
                price_drops=0,
            )
        assert repo.latest_site_runs()["Otoplus"]["status"] == "ok"


def test_legacy_cars_table_is_imported(settings, tmp_path):
    engine = create_db_engine(settings, url=f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE Cars (id INTEGER PRIMARY KEY, listing_id VARCHAR(50), source_site VARCHAR(50), "
                "brand TEXT, model TEXT, price BIGINT, year INT, km INT, tramer_fee BIGINT, scraped_at TEXT, link TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO Cars (listing_id, source_site, brand, model, price, year, km, tramer_fee, scraped_at, link) "
                "VALUES ('OP-9', 'Otoplus', 'Ford', 'Focus', 900000, 2018, 90000, 0, '2026-09-01 10:00:00', 'https://x')"
            )
        )
    init_db(engine)
    init_db(engine)  # idempotent
    rows = Repository(engine).list_listings()
    assert len(rows) == 1
    assert rows[0]["brand"] == "Ford" and rows[0]["tramer_fee"] is None
    assert rows[0]["is_new_listing"] is False
    engine.dispose()


def test_ping(repo: Repository):
    assert repo.ping() is True
