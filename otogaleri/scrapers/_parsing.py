"""Sitelerden bağımsız, saf ayrıştırma yardımcıları (birim testli)."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

_NEXT_F_PUSH = re.compile(r"self\.__next_f\.push\(\[1,(\".*?\")\]\)", re.S)


def next_flight_text(html: str) -> str:
    """Next.js App Router'ın ``self.__next_f.push([1, "..."])`` parçalarını birleştirir.

    Otoplus ve Otokoç sayfa verisini ``__NEXT_DATA__`` yerine bu "flight" akışında
    gönderiyor; parçalar JSON string literal'i olduğundan ``json.loads`` ile çözülür.
    """
    chunks: list[str] = []
    for match in _NEXT_F_PUSH.finditer(html):
        try:
            chunks.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return "".join(chunks)


def json_values_after(text: str, key: str) -> list[Any]:
    """``text`` içinde ``key`` (ör. ``'"results":['``) ile başlayan her JSON değerini çözer.

    ``key`` açılış parantezi (``[`` veya ``{``) ile bitmelidir; köşeli/süslü parantez
    dengesi string literal'leri hesaba katarak izlenir.
    """
    if not key or key[-1] not in "[{":
        raise ValueError("key '[' veya '{' ile bitmeli")
    values: list[Any] = []
    start = 0
    while (i := text.find(key, start)) >= 0:
        j = i + len(key) - 1
        end = _matching_bracket(text, j)
        if end is not None:
            try:
                values.append(json.loads(text[j : end + 1]))
            except json.JSONDecodeError:
                pass
        start = i + 1
    return values


def _matching_bracket(text: str, open_idx: int) -> int | None:
    depth = 0
    in_str = False
    escaped = False
    for k in range(open_idx, len(text)):
        ch = text[k]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return k
    return None


def jsonld_vehicles(html: str) -> list[dict[str, Any]]:
    """Sayfadaki tüm ``application/ld+json`` bloklarından ``Vehicle`` öğelerini toplar."""
    soup = BeautifulSoup(html, "lxml")
    vehicles: list[dict[str, Any]] = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items = data.get("@graph", [data])
        elif isinstance(data, list):
            items = data
        else:
            continue
        vehicles.extend(i for i in items if isinstance(i, dict) and i.get("@type") == "Vehicle")
    return vehicles


def to_int(value: Any, default: int = 0) -> int:
    """``"1.650.000 ₺"`` / ``"23.218 km"`` / ``2024`` / ``None`` → güvenli ``int``."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"\D", "", str(value))
    return int(digits) if digits else default


def brand_name(value: Any) -> str:
    """JSON-LD ``brand`` alanı hem ``{"name": ...}`` hem düz metin olabilir."""
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def humanize_slug(slug: str) -> str:
    """``"3-serisi"`` → ``"3 Serisi"``, ``"hs"`` → ``"HS"``, ``"c-elysee"`` → ``"C Elysee"``."""
    words = [w for w in slug.replace("_", "-").split("-") if w]
    return " ".join(w.upper() if len(w) <= 3 and not w.isdigit() else w.capitalize() for w in words)
