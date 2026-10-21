from __future__ import annotations

import threading
from datetime import timedelta

import pytest
import sqlalchemy as sa

from otogaleri.db import Repository, utcnow
from otogaleri.scan import CycleResult, ScanCriteria
from otogaleri.worker import ScanAlreadyRunningError, ScanManager, Worker


class CountingEngine:
    def __init__(self) -> None:
        self.cycles = 0

    def run_cycle(self, job_id, criteria, should_stop=lambda: False):  # type: ignore[no-untyped-def]
        self.cycles += 1
        return CycleResult()


@pytest.fixture
def fast_settings(monkeypatch, settings):  # type: ignore[no-untyped-def]
    settings.cycle_interval_sec = 0
    return settings


def _worker(repo, settings, engine):  # type: ignore[no-untyped-def]
    return Worker(repo, settings, engine_factory=lambda r, s: engine, worker_id="w-test")


class TestScanManager:
    def test_start_status_stop(self, repo: Repository, settings):
        mgr = ScanManager(repo, settings)
        job_id = mgr.start(ScanCriteria(brand="Fiat"))
        status = mgr.status()
        assert status["active"] is True
        assert status["session_id"] == job_id
        assert status["status"] == "pending"
        assert status["criteria"]["brand"] == "Fiat"
        assert mgr.stop() is True
        assert mgr.status()["active"] is False
        assert mgr.stop() is False

    def test_second_start_conflicts(self, repo: Repository, settings):
        mgr = ScanManager(repo, settings)
        mgr.start(ScanCriteria())
        with pytest.raises(ScanAlreadyRunningError):
            mgr.start(ScanCriteria())

    def test_orphaned_running_job_does_not_block(self, repo: Repository, settings):
        mgr = ScanManager(repo, settings)
        old = mgr.start(ScanCriteria())
        repo.claim_job("dead-worker", timedelta(seconds=60))
        with repo.engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE scan_jobs SET heartbeat_at = :t"),
                {"t": utcnow() - timedelta(hours=1)},
            )
        new = mgr.start(ScanCriteria())
        assert new != old
        assert repo.get_job(old)["status"] == "stopped"  # type: ignore[index]

    def test_idle_status(self, repo: Repository, settings):
        assert ScanManager(repo, settings).status() == {"active": False}


class TestWorker:
    def test_completes_when_duration_elapsed(self, repo: Repository, fast_settings):
        repo.create_job("j1", ScanCriteria().model_dump_json(), utcnow() - timedelta(seconds=1))
        job = repo.claim_job("w-test", timedelta(seconds=60))
        engine = CountingEngine()
        _worker(repo, fast_settings, engine).run_job(job, threading.Event())  # type: ignore[arg-type]
        assert repo.get_job("j1")["status"] == "completed"  # type: ignore[index]
        assert engine.cycles == 0

    def test_runs_cycles_until_stop_requested(self, repo: Repository, fast_settings):
        repo.create_job("j1", ScanCriteria().model_dump_json(), utcnow() + timedelta(hours=1))
        job = repo.claim_job("w-test", timedelta(seconds=60))

        class StopAfterTwo(CountingEngine):
            def run_cycle(self, job_id, criteria, should_stop=lambda: False):  # type: ignore[no-untyped-def]
                super().run_cycle(job_id, criteria, should_stop)
                if self.cycles == 2:
                    repo.request_stop(job_id, timedelta(seconds=60))
                return CycleResult()

        engine = StopAfterTwo()
        _worker(repo, fast_settings, engine).run_job(job, threading.Event())  # type: ignore[arg-type]
        final = repo.get_job("j1")
        assert final["status"] == "stopped"  # type: ignore[index]
        assert final["cycles"] == 2  # type: ignore[index]

    def test_process_shutdown_leaves_job_resumable(self, repo: Repository, fast_settings):
        repo.create_job("j1", ScanCriteria().model_dump_json(), utcnow() + timedelta(hours=1))
        job = repo.claim_job("w-test", timedelta(seconds=60))
        stop = threading.Event()
        stop.set()
        _worker(repo, fast_settings, CountingEngine()).run_job(job, stop)  # type: ignore[arg-type]
        assert repo.get_job("j1")["status"] == "running"  # type: ignore[index]

    def test_invalid_criteria_fails_job(self, repo: Repository, fast_settings):
        repo.create_job("j1", '{"sites": ["yok"]}', utcnow() + timedelta(hours=1))
        job = repo.claim_job("w-test", timedelta(seconds=60))
        _worker(repo, fast_settings, CountingEngine()).run_job(job, threading.Event())  # type: ignore[arg-type]
        assert repo.get_job("j1")["status"] == "failed"  # type: ignore[index]

    def test_run_forever_picks_up_job_and_exits_on_stop(self, repo: Repository, fast_settings):
        fast_settings.worker_poll_sec = 0.05
        repo.create_job("j1", ScanCriteria().model_dump_json(), utcnow() - timedelta(seconds=1))
        stop = threading.Event()
        t = threading.Thread(
            target=_worker(repo, fast_settings, CountingEngine()).run_forever, args=(stop,)
        )
        t.start()
        for _ in range(100):
            if repo.get_job("j1")["status"] == "completed":  # type: ignore[index]
                break
            threading.Event().wait(0.05)
        stop.set()
        t.join(timeout=5)
        assert not t.is_alive()
        assert repo.get_job("j1")["status"] == "completed"  # type: ignore[index]


def test_cycle_counts_are_recorded_and_accumulated(repo: Repository, fast_settings):
    from otogaleri.scan import SiteResult

    repo.create_job("j1", ScanCriteria().model_dump_json(), utcnow() + timedelta(hours=1))
    job = repo.claim_job("w-test", timedelta(seconds=60))

    class TwoCycles(CountingEngine):
        def run_cycle(self, job_id, criteria, should_stop=lambda: False):  # type: ignore[no-untyped-def]
            super().run_cycle(job_id, criteria, should_stop)
            if self.cycles == 2:
                repo.request_stop(job_id, timedelta(seconds=60))
            new = 3 if self.cycles == 1 else 1
            return CycleResult(
                [
                    SiteResult("Otoplus", seen=40, matched=5, new=new),
                    SiteResult("Arabam.com", seen=10, matched=2),
                ]
            )

    _worker(repo, fast_settings, TwoCycles()).run_job(job, threading.Event())  # type: ignore[arg-type]
    final = repo.get_job("j1")
    assert final["cycles"] == 2  # type: ignore[index]
    assert final["last_cycle_seen"] == 50  # type: ignore[index]
    assert final["last_cycle_matched"] == 7  # type: ignore[index]
    assert final["last_cycle_new"] == 1  # type: ignore[index]
    assert final["found_total"] == 4  # type: ignore[index]
    status = ScanManager(repo, fast_settings).status()
    assert (status["found_total"], status["last_cycle_new"]) == (4, 1)
