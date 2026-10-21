"""Bildirim kanalları: masaüstü (Windows toast), Telegram, e-posta (SMTP) ve log.

:class:`Notifier` olayları (:class:`NewListing`, :class:`PriceDrop`,
:class:`SiteFailure`) etkin tüm kanallara dağıtır. Bir kanalın hatası diğerlerini
etkilemez. Site hata bildirimleri site başına ``failure_cooldown_minutes`` ile
seyreltilir; ``OTOGALERI_NOTIFICATIONS_ENABLED=false`` hepsini susturur.
"""

from __future__ import annotations

import json
import logging
import platform
import smtplib
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from otogaleri.config import Settings, get_settings
from otogaleri.formatting import format_price
from otogaleri.models import Listing

log = logging.getLogger(__name__)


# ==========================================================================
#  OLAYLAR
# ==========================================================================


@dataclass(frozen=True)
class NewListing:
    listing: Listing
    deal_pct: float | None = None

    def render(self) -> tuple[str, str]:
        item = self.listing
        lines = [
            f"{item.display_name} · {item.year} · {item.km:,} km".replace(",", "."),
            f"Fiyat: {format_price(item.price)}",
            f"Boya: {item.damage_columns()['painted_parts']} | "
            f"Değişen: {item.damage_columns()['changed_parts']}",
        ]
        if item.tramer is not None:
            lines.append(f"Tramer: {format_price(item.tramer)}")
        if self.deal_pct is not None and self.deal_pct >= 3:
            lines.append(f"Piyasa medyanının %{self.deal_pct:.0f} altında")
        lines.append(item.link)
        return f"🚨 Yeni araç · {item.source_site}", "\n".join(lines)


@dataclass(frozen=True)
class PriceDrop:
    listing: Listing
    old_price: int

    @property
    def drop_pct(self) -> float:
        return (self.old_price - self.listing.price) / self.old_price * 100 if self.old_price else 0

    def render(self) -> tuple[str, str]:
        item = self.listing
        body = (
            f"{item.display_name} · {item.year}\n"
            f"{format_price(self.old_price)} → {format_price(item.price)} "
            f"(-%{self.drop_pct:.1f})\n{item.link}"
        )
        return f"📉 Fiyat düştü · {item.source_site}", body


@dataclass(frozen=True)
class SiteFailure:
    site: str
    reason: str

    def render(self) -> tuple[str, str]:
        return f"⚠️ {self.site} taramasında sorun", f"Sebep: {self.reason[:300]}"


Event = NewListing | PriceDrop | SiteFailure


# ==========================================================================
#  KANALLAR
# ==========================================================================


class Channel(Protocol):
    name: str

    def send(self, title: str, body: str) -> None: ...


class LogChannel:
    name = "log"

    def send(self, title: str, body: str) -> None:
        log.info("[Bildirim] %s | %s", title, body.replace("\n", " | "))


class DesktopChannel:
    name = "desktop"

    def send(self, title: str, body: str) -> None:
        from win11toast import toast

        toast(title, body, app_id="OtoGaleri Avcı Botu")


class TelegramChannel:
    name = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id
        self._opener = opener

    def send(self, title: str, body: str) -> None:
        payload = json.dumps(
            {
                "chat_id": self._chat_id,
                "text": f"{title}\n{body}",
                "disable_web_page_preview": False,
            }
        ).encode()
        req = urllib.request.Request(
            self._url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        self._opener(req, timeout=15)


class EmailChannel:
    name = "email"

    def __init__(
        self, settings: Settings, smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP
    ):
        self._s = settings
        self._smtp_factory = smtp_factory

    def send(self, title: str, body: str) -> None:
        s = self._s
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = s.smtp_from or s.smtp_user
        msg["To"] = s.smtp_to
        msg.set_content(body)
        with self._smtp_factory(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


def default_channels(settings: Settings) -> list[Channel]:
    channels: list[Channel] = [LogChannel()]
    if settings.desktop_notifications and platform.system() == "Windows":
        channels.append(DesktopChannel())
    if settings.telegram_enabled:
        channels.append(TelegramChannel(settings.telegram_bot_token, settings.telegram_chat_id))
    if settings.email_enabled:
        channels.append(EmailChannel(settings))
    return channels


# ==========================================================================
#  DAĞITICI
# ==========================================================================


class Notifier:
    def __init__(
        self,
        settings: Settings | None = None,
        channels: list[Channel] | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.settings = settings or get_settings()
        self.channels = channels if channels is not None else default_channels(self.settings)
        self._clock = clock
        self._last_failure: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def notify(self, event: Event) -> bool:
        """Olayı gönderir; susturulduysa (kill-switch / cooldown) ``False`` döner."""
        if not self.settings.notifications_enabled:
            return False
        if isinstance(event, SiteFailure) and not self._failure_allowed(event.site):
            log.info("[Bildirim] %s hata bildirimi cooldown'da, atlandi.", event.site)
            return False
        title, body = event.render()
        for channel in self.channels:
            try:
                channel.send(title, body)
            except Exception:
                log.exception("[Bildirim] '%s' kanali gonderemedi.", channel.name)
        return True

    def _failure_allowed(self, site: str) -> bool:
        now = self._clock()
        cooldown = timedelta(minutes=self.settings.failure_cooldown_minutes)
        with self._lock:
            last = self._last_failure.get(site)
            if last is not None and now - last < cooldown:
                return False
            self._last_failure[site] = now
            return True
