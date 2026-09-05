import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from db import _is_retryable, retry_on_db_error


def _op_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection reset"))


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception("duplicate key"))


class TestIsRetryable:
    def test_operational_error_is_retryable(self):
        assert _is_retryable(_op_error()) is True

    def test_integrity_error_is_not_retryable(self):
        assert _is_retryable(_integrity_error()) is False

    def test_programming_error_is_not_retryable(self):
        assert _is_retryable(ProgrammingError("x", {}, Exception("bad col"))) is False

    def test_unexpected_error_is_not_retryable(self):
        assert _is_retryable(KeyError("nope")) is False


class TestRetryDecorator:
    def test_retries_transient_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("db.time.sleep", lambda _s: None)
        calls = {"n": 0}

        @retry_on_db_error(max_retries=3, backoff_factor=1)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _op_error()
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3

    def test_does_not_retry_integrity_error(self, monkeypatch):
        monkeypatch.setattr("db.time.sleep", lambda _s: None)
        calls = {"n": 0}

        @retry_on_db_error(max_retries=3, backoff_factor=1)
        def dup_insert():
            calls["n"] += 1
            raise _integrity_error()

        with pytest.raises(IntegrityError):
            dup_insert()
        assert calls["n"] == 1  # tek deneme, boşuna bekleme yok

    def test_raises_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setattr("db.time.sleep", lambda _s: None)

        @retry_on_db_error(max_retries=2, backoff_factor=1)
        def always_down():
            raise _op_error()

        with pytest.raises(OperationalError):
            always_down()
