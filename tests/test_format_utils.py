from format_utils import format_try


def test_thousands_and_decimal_separators():
    assert format_try(34980.5) == "34.980,50"
    assert format_try(1234567.89) == "1.234.567,89"


def test_small_and_zero_values():
    assert format_try(0) == "0,00"
    assert format_try(5) == "5,00"


def test_invalid_input_falls_back_to_zero():
    assert format_try(None) == "0,00"
    assert format_try("not-a-number") == "0,00"


def test_numeric_string_is_accepted():
    assert format_try("2500") == "2.500,00"
