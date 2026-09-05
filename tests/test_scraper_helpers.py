from scrapers import _safe_int, check_part_allowed, extract_damaged_parts


class TestSafeInt:
    def test_parses_plain_int_and_numeric_string(self):
        assert _safe_int(42) == 42
        assert _safe_int("42") == 42

    def test_returns_default_on_none_or_garbage(self):
        assert _safe_int(None) == 0
        assert _safe_int("abc") == 0
        assert _safe_int("", default=-1) == -1

    def test_truncates_float(self):
        assert _safe_int(12.9) == 12


class TestCheckPartAllowed:
    def test_clean_text_is_always_allowed(self):
        assert check_part_allowed("araç tertemiz", "kaput", []) is True

    def test_painted_part_not_in_allowlist_is_rejected(self):
        text = "kaput boyalı"
        assert check_part_allowed(text, "kaput", []) is False

    def test_painted_part_in_allowlist_is_allowed(self):
        text = "kaput boyalı"
        assert check_part_allowed(text, "kaput", ["kaput"]) is True


class TestExtractDamagedParts:
    def test_no_damage_returns_sentinel(self):
        assert extract_damaged_parts("orijinal hatasiz arac") == "Bilinmiyor/Metinde Yok"

    def test_detects_painted_part(self):
        out = extract_damaged_parts("sağ ön kapı boyalı, tavan değişmiş")
        assert "Sağ Ön Kapı" in out
        assert "Tavan" in out
