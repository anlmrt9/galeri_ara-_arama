"""Site hata bildirimi cooldown mantığı (masaüstü toast'a bağımlı değil)."""

from datetime import datetime, timedelta

import notifications
from notifications import send_site_failure_notification


def _sink(monkeypatch):
    """toast/log yolunu yakala; platformu Windows-dışı yaparak logger.warning'e düşür."""
    monkeypatch.setattr(notifications.platform, "system", lambda: "Linux")
    seen: list[str] = []
    monkeypatch.setattr(notifications.logger, "warning", lambda msg, *a: seen.append(str(msg)))
    monkeypatch.setattr(notifications.logger, "info", lambda msg, *a: seen.append(str(msg)))
    return seen


def test_first_notification_is_sent(monkeypatch):
    notifications._failure_notify_last_sent.clear()
    seen = _sink(monkeypatch)
    send_site_failure_notification("Otoplus", "HTTP 500")
    assert any("Otoplus" in s for s in seen)


def test_second_notification_within_cooldown_is_suppressed(monkeypatch):
    notifications._failure_notify_last_sent.clear()
    seen = _sink(monkeypatch)
    send_site_failure_notification("Otoplus", "HTTP 500")
    seen.clear()
    send_site_failure_notification("Otoplus", "HTTP 500 again")
    assert all("cooldown" in s.lower() for s in seen) or seen == []
    assert not any("Sebep: HTTP 500 again" in s for s in seen)


def test_notification_after_cooldown_elapsed_is_sent(monkeypatch):
    notifications._failure_notify_last_sent.clear()
    seen = _sink(monkeypatch)
    stale = datetime.now() - timedelta(
        minutes=notifications.SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES + 1
    )
    notifications._failure_notify_last_sent["VavaCars"] = stale
    send_site_failure_notification("VavaCars", "timeout")
    assert any("VavaCars" in s for s in seen)


def test_cooldown_is_per_site(monkeypatch):
    notifications._failure_notify_last_sent.clear()
    seen = _sink(monkeypatch)
    send_site_failure_notification("Otoplus", "err")
    seen.clear()
    send_site_failure_notification("Otokoç 2. El", "err")
    assert any("Otokoç" in s for s in seen)
