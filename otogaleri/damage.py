"""Kaporta hasar modeli: parça normalizasyonu, durum sınıflandırma, filtre kararı.

Siteler hasar bilgisini farklı biçimlerde verir (Otoplus: ``front_left_door`` +
``["painted"]``; Otokoç: ``"Sol Ön Kapı"`` + ``"Painted"``; Arabam: ``"Sol Ön Kapı"`` +
``"painted"``/``"changed"``/``"notset"``). Bu modül hepsini tek bir sözlüğe indirger:
13 kanonik parça kimliği (hasar haritası bileşeniyle birebir aynı) → :class:`DamageState`.

Eski sürüm sayfanın *tüm metninde* "boya" kelimesini arıyordu; Otoplus'ın her ilanda
gösterdiği "Boyalı 0 / Değişen 0" etiketi yüzünden hasarsız araç istendiğinde bütün
Otoplus ilanları eleniyordu. Artık yalnızca yapılandırılmış ekspertiz verisi okunuyor.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum


class DamageState(str, Enum):
    ORIGINAL = "original"
    COSMETIC = "cosmetic"  # çizik, ezik, göçük, dolu... (boya/değişen değil)
    PAINTED = "painted"  # boyalı veya lokal boyalı
    CHANGED = "changed"  # değişen
    UNKNOWN = "unknown"  # satıcı belirtmemiş


#: Kötüden iyiye değil, "ağırlık" sırası — birden çok etiket gelirse en ağırı seçilir.
_SEVERITY = {
    DamageState.UNKNOWN: 0,
    DamageState.ORIGINAL: 1,
    DamageState.COSMETIC: 2,
    DamageState.PAINTED: 3,
    DamageState.CHANGED: 4,
}

#: (kimlik, etiket) — ``car_map_component`` ve ``/api/config`` ile aynı sıra.
PARTS: tuple[tuple[str, str], ...] = (
    ("on_tampon", "Ön Tampon"),
    ("kaput", "Kaput"),
    ("tavan", "Tavan"),
    ("bagaj", "Bagaj"),
    ("arka_tampon", "Arka Tampon"),
    ("sol_on_cam", "Sol Ön Çamurluk"),
    ("sag_on_cam", "Sağ Ön Çamurluk"),
    ("sol_on_kapi", "Sol Ön Kapı"),
    ("sag_on_kapi", "Sağ Ön Kapı"),
    ("sol_arka_kapi", "Sol Arka Kapı"),
    ("sag_arka_kapi", "Sağ Arka Kapı"),
    ("sol_arka_cam", "Sol Arka Çamurluk"),
    ("sag_arka_cam", "Sağ Arka Çamurluk"),
)
PART_IDS: tuple[str, ...] = tuple(p for p, _ in PARTS)
PART_LABELS: dict[str, str] = dict(PARTS)

_TR_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")


def slugify(text: str) -> str:
    """``"Mercedes-Benz"`` → ``"mercedes-benz"``, ``"Otokoç 2. El"`` → ``"otokoc-2-el"``."""
    text = unicodedata.normalize("NFC", str(text)).translate(_TR_FOLD).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def fold(text: str) -> str:
    """Karşılaştırma anahtarı: Türkçe karakterleri sadeleştirir, harf/rakam dışını atar.

    ``"Sağ Arka Çamurluk"`` → ``"sagarkacamurluk"``, ``"3 Serisi"`` → ``"3serisi"``.
    """
    text = unicodedata.normalize("NFC", str(text)).translate(_TR_FOLD).lower()
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _aliases() -> dict[str, str]:
    table: dict[str, list[str]] = {
        "on_tampon": ["ontampon", "front_bumper", "frontbumper"],
        "kaput": ["kaput", "motorkaputu", "onkaput", "hood", "fronthood"],
        "tavan": ["tavan", "ceiling", "roof"],
        "bagaj": [
            "bagaj",
            "bagajkapagi",
            "bagajkaputu",
            "arkakaput",
            "tailgate",
            "tailboard",
            "rearhood",
        ],
        "arka_tampon": ["arkatampon", "rear_bumper", "rearbumper"],
        "sol_on_cam": ["solon camurluk", "front_left_mudguard", "frontleftfender"],
        "sag_on_cam": ["sagoncamurluk", "front_right_mudguard", "frontrightfender"],
        "sol_on_kapi": ["solonkapi", "front_left_door", "leftfrontdoor"],
        "sag_on_kapi": ["sagonkapi", "front_right_door", "rightfrontdoor"],
        "sol_arka_kapi": ["solarkakapi", "rear_left_door", "leftbackdoor", "leftreardoor"],
        "sag_arka_kapi": ["sagarkakapi", "rear_right_door", "rightbackdoor", "rightreardoor"],
        "sol_arka_cam": ["solarkacamurluk", "rear_left_mudguard", "rearleftfender"],
        "sag_arka_cam": ["sagarkacamurluk", "rear_right_mudguard", "rearrightfender"],
    }
    out: dict[str, str] = {}
    for part_id, names in table.items():
        out[fold(part_id)] = part_id
        out[fold(PART_LABELS[part_id])] = part_id
        for name in names:
            out[fold(name)] = part_id
    # Otoplus kendi verisinde "Sol Ark Kapı" yazım hatası yapıyor
    out[fold("Sol Ark Kapı")] = "sol_arka_kapi"
    return out


_PART_ALIASES = _aliases()


def normalize_part(name: str | None) -> str | None:
    """Herhangi bir parça adını/kodunu kanonik kimliğe çevirir; tanınmazsa ``None``."""
    if not name:
        return None
    return _PART_ALIASES.get(fold(name))


_CHANGED_WORDS = ("changed", "replaced", "degis", "degismis", "degisen")
_PAINTED_WORDS = ("paint", "boya")
_ORIGINAL_WORDS = ("good", "original", "orijinal", "orginal", "hatasiz", "none")
_UNKNOWN_WORDS = ("notset", "belirtilmemis", "unknown", "bilinmiyor")
#: "boyasız", "değişensiz" gibi olumsuzlanmış ifadeler "boya"/"değiş" içerse de orijinaldir.
_NEGATED_WORDS = ("boyasiz", "degisensiz", "hasarsiz", "notpainted", "notchanged")


def classify(value: str | None) -> DamageState:
    """Tek bir site etiketini :class:`DamageState`'e çevirir."""
    if value is None:
        return DamageState.UNKNOWN
    key = fold(value)
    if not key:
        return DamageState.UNKNOWN
    if any(w in key for w in _UNKNOWN_WORDS):
        return DamageState.UNKNOWN
    if any(w in key for w in _NEGATED_WORDS):
        return DamageState.ORIGINAL
    if any(w in key for w in _CHANGED_WORDS):
        return DamageState.CHANGED
    if any(w in key for w in _PAINTED_WORDS):
        return DamageState.PAINTED
    if any(key == w or key.startswith(w) for w in _ORIGINAL_WORDS):
        return DamageState.ORIGINAL
    # çizik / ezik / göçük / dolu / kırık / hit_major ... → kozmetik
    return DamageState.COSMETIC


def worst(states: Iterable[DamageState]) -> DamageState:
    states = list(states)
    if not states:
        return DamageState.UNKNOWN
    return max(states, key=_SEVERITY.__getitem__)


@dataclass
class DamageReport:
    """Bir ilanın parça bazlı hasar durumu + tramer bilgisi.

    ``parts`` yalnızca bilinen parçaları içerir. Bir parça hiç yoksa durumu bilinmiyor
    demektir — ``default`` ile (ör. Otokoç yalnızca hasarlı parçaları listeler) doldurulabilir.
    """

    parts: dict[str, DamageState] = field(default_factory=dict)
    tramer: int | None = None
    source_note: str = ""
    #: "Ağır hasar kayıtlı" (pert / ağır hasar) beyanı — her zaman elenir
    heavy_damage: bool = False

    @classmethod
    def all_original(cls, *, tramer: int | None = None, note: str = "") -> DamageReport:
        return cls(dict.fromkeys(PART_IDS, DamageState.ORIGINAL), tramer=tramer, source_note=note)

    def set(self, part_id: str, state: DamageState) -> None:
        current = self.parts.get(part_id)
        self.parts[part_id] = state if current is None else worst([current, state])

    @property
    def is_known(self) -> bool:
        return any(s is not DamageState.UNKNOWN for s in self.parts.values())

    def parts_in(self, state: DamageState) -> list[str]:
        return [p for p in PART_IDS if self.parts.get(p) is state]

    @property
    def painted(self) -> list[str]:
        return self.parts_in(DamageState.PAINTED)

    @property
    def changed(self) -> list[str]:
        return self.parts_in(DamageState.CHANGED)

    def label(self, state: DamageState) -> str:
        """İnsan okunur liste: ``"Kaput, Tavan"`` / ``"Orijinal"`` / ``"Bilinmiyor"``."""
        if not self.is_known:
            return "Bilinmiyor"
        names = [PART_LABELS[p] for p in self.parts_in(state)]
        return ", ".join(names) if names else "Yok"

    def to_dict(self) -> dict[str, object]:
        return {
            "parts": {p: s.value for p, s in self.parts.items()},
            "tramer": self.tramer,
            "note": self.source_note,
            "heavy_damage": self.heavy_damage,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object] | None) -> DamageReport | None:
        if not data:
            return None
        raw_parts = data.get("parts") or {}
        parts = {
            str(k): DamageState(str(v))
            for k, v in dict(raw_parts).items()  # type: ignore[call-overload]
            if str(v) in DamageState._value2member_map_
        }
        tramer = data.get("tramer")
        return cls(
            parts,
            tramer=int(tramer) if isinstance(tramer, (int, float)) else None,
            source_note=str(data.get("note") or ""),
            heavy_damage=bool(data.get("heavy_damage")),
        )


@dataclass(frozen=True)
class DamagePolicy:
    """Kullanıcının hasar toleransı.

    * ``paint_ok``  — boyalı (veya lokal boyalı) olmasına izin verilen parçalar
    * ``change_ok`` — değişen olmasına da izin verilen parçalar (boya da serbesttir)
    * ``max_tramer`` — kabul edilen azami tramer (TL)
    * ``include_unknown`` — hasar bilgisi okunamayan ilanlar gösterilsin mi
    """

    paint_ok: frozenset[str] = frozenset()
    change_ok: frozenset[str] = frozenset()
    max_tramer: float | None = None
    include_unknown: bool = True


def evaluate(report: DamageReport | None, policy: DamagePolicy) -> tuple[bool, str]:
    """İlan politikaya uyuyor mu? ``(uygun_mu, red_sebebi)`` döner."""
    if report is not None and report.heavy_damage:
        return False, "ağır hasar kayıtlı"
    if report is None or not report.is_known:
        if report is not None and report.tramer is not None and policy.max_tramer is not None:
            if report.tramer > policy.max_tramer:
                return False, f"tramer {report.tramer} > {policy.max_tramer:.0f}"
        if policy.include_unknown:
            return True, ""
        return False, "hasar bilgisi okunamadı"

    for part_id, state in report.parts.items():
        if state is DamageState.CHANGED and part_id not in policy.change_ok:
            return False, f"{PART_LABELS.get(part_id, part_id)} değişen"
        if state is DamageState.PAINTED and not (
            part_id in policy.paint_ok or part_id in policy.change_ok
        ):
            return False, f"{PART_LABELS.get(part_id, part_id)} boyalı"

    if report.tramer is not None and policy.max_tramer is not None:
        if report.tramer > policy.max_tramer:
            return False, f"tramer {report.tramer} > {policy.max_tramer:.0f}"
    return True, ""
