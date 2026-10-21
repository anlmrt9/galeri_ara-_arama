from __future__ import annotations

import json
from datetime import datetime, timedelta

from otogaleri.damage import DamageReport
from otogaleri.models import Listing
from otogaleri.notifications import (
    EmailChannel,
    NewListing,
    Notifier,
    PriceDrop,
    SiteFailure,
    TelegramChannel,
    default_channels,
)


def _listing(price: int = 1_250_000) -> Listing:
    return Listing(
        "Otoplus",
        "OP-1",
        "https://example.com/1",
        brand="Fiat",
        model="Egea",
        year=2021,
        km=45_000,
        price=price,
        damage=DamageReport.all_original(tramer=0),
    )


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0)

    def __call__(self) -> datetime:
        return self.now


def test_new_listing_message():
    title, body = NewListing(_listing(), deal_pct=8).render()
    assert "Yeni araç" in title and "Otoplus" in title
    assert "1.250.000 ₺" in body and "45.000 km" in body
    assert "%8 altında" in body
    assert "https://example.com/1" in body


def test_price_drop_message():
    event = PriceDrop(_listing(900_000), old_price=1_000_000)
    assert round(event.drop_pct) == 10
    title, body = event.render()
    assert "Fiyat düştü" in title and "1.000.000 ₺ → 900.000 ₺" in body


def test_kill_switch(settings, channel):
    settings.notifications_enabled = False
    assert Notifier(settings, [channel]).notify(SiteFailure("Otoplus", "x")) is False
    assert channel.sent == []


def test_failure_cooldown_per_site(settings, channel):
    clock = Clock()
    n = Notifier(settings, [channel], clock=clock)
    assert n.notify(SiteFailure("Otoplus", "HTTP 500"))
    assert not n.notify(SiteFailure("Otoplus", "HTTP 500"))
    assert n.notify(SiteFailure("Arabam.com", "HTTP 500"))
    clock.now += timedelta(minutes=settings.failure_cooldown_minutes + 1)
    assert n.notify(SiteFailure("Otoplus", "HTTP 500"))
    assert len(channel.sent) == 3


def test_broken_channel_does_not_block_others(settings, channel):
    class Broken:
        name = "broken"

        def send(self, title, body):  # type: ignore[no-untyped-def]
            raise OSError("down")

    assert Notifier(settings, [Broken(), channel]).notify(NewListing(_listing()))
    assert len(channel.sent) == 1


def test_telegram_payload():
    captured = {}

    def opener(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"], captured["body"] = req.full_url, json.loads(req.data)

    TelegramChannel("TOKEN", "42", opener=opener).send("Başlık", "Gövde")
    assert captured["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert captured["body"]["chat_id"] == "42"
    assert captured["body"]["text"] == "Başlık\nGövde"


def test_email_channel(settings):
    settings.smtp_host, settings.smtp_user, settings.smtp_password = "smtp.test", "bot@test", "pw"
    settings.smtp_to = "me@test"
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):  # type: ignore[no-untyped-def]
            sent["host"] = host

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *a):  # type: ignore[no-untyped-def]
            return False

        def starttls(self):  # type: ignore[no-untyped-def]
            sent["tls"] = True

        def login(self, user, pw):  # type: ignore[no-untyped-def]
            sent["login"] = user

        def send_message(self, msg):  # type: ignore[no-untyped-def]
            sent["subject"], sent["to"] = msg["Subject"], msg["To"]

    EmailChannel(settings, smtp_factory=FakeSMTP).send("Konu", "Metin")
    assert sent == {
        "host": "smtp.test",
        "tls": True,
        "login": "bot@test",
        "subject": "Konu",
        "to": "me@test",
    }


def test_default_channels_follow_settings(settings):
    assert [c.name for c in default_channels(settings)] == ["log"]
    settings.telegram_bot_token, settings.telegram_chat_id = "t", "1"
    settings.smtp_host, settings.smtp_to, settings.smtp_from = "h", "to@x", "from@x"
    assert [c.name for c in default_channels(settings)] == ["log", "telegram", "email"]
