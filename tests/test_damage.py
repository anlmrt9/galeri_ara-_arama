from __future__ import annotations

import pytest

from otogaleri.damage import (
    PART_IDS,
    DamagePolicy,
    DamageReport,
    DamageState,
    classify,
    evaluate,
    fold,
    normalize_part,
    slugify,
)


def test_fold_and_slugify():
    assert fold("Sağ Arka Çamurluk") == "sagarkacamurluk"
    assert fold("3 Serisi") == "3serisi"
    assert slugify("Mercedes-Benz") == "mercedes-benz"
    assert slugify("Otokoç 2. El") == "otokoc-2-el"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Motor Kaputu", "kaput"),
        ("hood", "kaput"),
        ("Bagaj Kapağı", "bagaj"),
        ("Tailboard", "bagaj"),
        ("SağArkaÇamurluk", "sag_arka_cam"),
        ("front_left_mudguard", "sol_on_cam"),
        ("Sol Ark Kapı", "sol_arka_kapi"),  # Otoplus yazım hatası
        ("ÖnTampon", "on_tampon"),
        ("sol ön çamurluk", "sol_on_cam"),  # 1.x API'nin gönderdiği ad
        ("sol_on_kapi", "sol_on_kapi"),
        ("Sol Ön Far", None),
        ("", None),
    ],
)
def test_normalize_part(name, expected):
    assert normalize_part(name) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("good", DamageState.ORIGINAL),
        ("painted", DamageState.PAINTED),
        ("Local Painted", DamageState.PAINTED),
        ("Boyanmış", DamageState.PAINTED),
        ("Replaced", DamageState.CHANGED),
        ("changed", DamageState.CHANGED),
        ("Değişmiş", DamageState.CHANGED),
        ("notset", DamageState.UNKNOWN),
        ("Belirtilmemiş", DamageState.UNKNOWN),
        ("scratch", DamageState.COSMETIC),
        ("hit_major", DamageState.COSMETIC),
        ("Boyasız", DamageState.ORIGINAL),
        (None, DamageState.UNKNOWN),
    ],
)
def test_classify(value, expected):
    assert classify(value) is expected


def _report(**parts: DamageState) -> DamageReport:
    report = DamageReport.all_original()
    for k, v in parts.items():
        report.parts[k] = v
    return report


class TestEvaluate:
    def test_clean_car_passes_strict_policy(self):
        assert evaluate(DamageReport.all_original(), DamagePolicy()) == (True, "")

    def test_cosmetic_damage_is_not_rejected(self):
        assert evaluate(_report(kaput=DamageState.COSMETIC), DamagePolicy())[0]

    def test_painted_part_rejected_unless_allowed(self):
        report = _report(kaput=DamageState.PAINTED)
        ok, reason = evaluate(report, DamagePolicy())
        assert not ok and "Kaput" in reason
        assert evaluate(report, DamagePolicy(paint_ok=frozenset({"kaput"})))[0]

    def test_changed_part_needs_change_permission(self):
        report = _report(kaput=DamageState.CHANGED)
        assert not evaluate(report, DamagePolicy(paint_ok=frozenset({"kaput"})))[0]
        assert evaluate(report, DamagePolicy(change_ok=frozenset({"kaput"})))[0]

    def test_change_permission_implies_paint_permission(self):
        report = _report(kaput=DamageState.PAINTED)
        assert evaluate(report, DamagePolicy(change_ok=frozenset({"kaput"})))[0]

    def test_tramer_limit(self):
        report = DamageReport.all_original(tramer=20_000)
        assert not evaluate(report, DamagePolicy(max_tramer=15_000))[0]
        assert evaluate(report, DamagePolicy(max_tramer=25_000))[0]

    def test_unknown_damage_follows_include_unknown(self):
        assert evaluate(None, DamagePolicy(include_unknown=True))[0]
        assert not evaluate(None, DamagePolicy(include_unknown=False))[0]

    def test_unknown_report_with_tramer_over_limit_is_rejected(self):
        report = DamageReport(tramer=50_000)
        assert not evaluate(report, DamagePolicy(max_tramer=10_000))[0]


def test_report_roundtrip_and_labels():
    report = _report(kaput=DamageState.PAINTED, tavan=DamageState.CHANGED)
    report.tramer = 1200
    again = DamageReport.from_dict(report.to_dict())
    assert again is not None
    assert again.parts == report.parts and again.tramer == 1200
    assert again.label(DamageState.PAINTED) == "Kaput"
    assert again.label(DamageState.CHANGED) == "Tavan"
    assert DamageReport().label(DamageState.PAINTED) == "Bilinmiyor"
    assert set(again.parts) == set(PART_IDS)


def test_set_keeps_worst_state():
    report = DamageReport()
    report.set("kaput", DamageState.PAINTED)
    report.set("kaput", DamageState.COSMETIC)
    assert report.parts["kaput"] is DamageState.PAINTED
