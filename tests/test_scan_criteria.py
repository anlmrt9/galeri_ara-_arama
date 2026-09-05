import pytest
from pydantic import ValidationError

from config import ALL_SITES
from scan_service import (
    DEFAULT_DURATION_HOURS,
    DEFAULT_MAX_PRICE,
    DEFAULT_MIN_YEAR,
    ScanCriteria,
)


def test_defaults_cover_all_sites():
    c = ScanCriteria()
    assert c.sites == list(ALL_SITES)
    assert c.brand == "Tümü"
    assert c.max_price == DEFAULT_MAX_PRICE
    assert c.duration_hours == DEFAULT_DURATION_HOURS


def test_from_optional_fills_none_with_defaults():
    c = ScanCriteria.from_optional(brand="BMW", min_price=None, max_price=500_000)
    assert c.brand == "BMW"
    assert c.min_price == 0
    assert c.max_price == 500_000
    assert c.min_year == DEFAULT_MIN_YEAR


def test_to_scraper_dict_uses_duration_key():
    d = ScanCriteria(duration_hours=12).to_scraper_dict()
    assert d["duration"] == 12
    assert "duration_hours" not in d
    assert set(d) == {
        "sites",
        "brand",
        "model",
        "min_price",
        "max_price",
        "min_year",
        "max_year",
        "min_km",
        "max_km",
        "max_tramer",
        "duration",
        "allowed_parts",
    }


def test_rejects_inverted_price_range():
    with pytest.raises(ValidationError):
        ScanCriteria(min_price=100, max_price=50)


def test_rejects_inverted_year_range():
    with pytest.raises(ValidationError):
        ScanCriteria(min_year=2024, max_year=2000)


def test_rejects_unknown_site():
    with pytest.raises(ValidationError):
        ScanCriteria(sites=["Sahibinden", "TotallyFakeSite"])


def test_rejects_non_positive_duration():
    with pytest.raises(ValidationError):
        ScanCriteria(duration_hours=0)


def test_empty_sites_falls_back_to_all():
    assert ScanCriteria(sites=[]).sites == list(ALL_SITES)
