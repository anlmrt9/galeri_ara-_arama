"""Piyasa referansı ve fırsat skoru.

Kayıtlı ilanlardan (marka, model, yıl) grubu için medyan fiyat çıkarılır; grup
küçükse (marka, model) grubuna düşülür. Fırsat skoru, ilan fiyatının bu medyanın
yüzde kaç altında olduğudur (negatifse üstünde).

Not: Referans yalnızca *kayıtlı* ilanlardan hesaplanır, yani tüm piyasayı değil
botun gördüğü ve kriterlere uyan ilanları yansıtır.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from statistics import median
from typing import Any

from otogaleri.damage import fold

MIN_SAMPLES = 3


@dataclass(frozen=True)
class MarketReference:
    by_year: dict[tuple[str, str, int], float]
    by_model: dict[tuple[str, str], float]

    def median_for(self, brand: str, model: str, year: int) -> float | None:
        b, m = fold(brand), fold(model)
        return self.by_year.get((b, m, int(year or 0))) or self.by_model.get((b, m))

    def deal_pct(self, brand: str, model: str, year: int, price: float) -> float | None:
        ref = self.median_for(brand, model, year)
        if not ref or not price:
            return None
        return round((ref - float(price)) / ref * 100, 1)


def build_reference(rows: Iterable[Mapping[str, Any]]) -> MarketReference:
    by_year: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    by_model: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        price = float(r.get("price") or 0)
        if price <= 0:
            continue
        b, m = fold(str(r.get("brand") or "")), fold(str(r.get("model") or ""))
        if not b or not m:
            continue
        by_year[(b, m, int(r.get("year") or 0))].append(price)
        by_model[(b, m)].append(price)
    return MarketReference(
        by_year={k: median(v) for k, v in by_year.items() if len(v) >= MIN_SAMPLES},
        by_model={k: median(v) for k, v in by_model.items() if len(v) >= MIN_SAMPLES},
    )


def annotate(
    rows: list[dict[str, Any]], reference: MarketReference | None = None
) -> list[dict[str, Any]]:
    """Her satıra ``market_median`` ve ``deal_pct`` ekler (yerinde) ve listeyi döndürür."""
    reference = reference or build_reference(rows)
    for r in rows:
        r["market_median"] = reference.median_for(
            r.get("brand", ""), r.get("model", ""), r.get("year", 0)
        )
        r["deal_pct"] = reference.deal_pct(
            r.get("brand", ""), r.get("model", ""), r.get("year", 0), r.get("price", 0)
        )
    return rows
