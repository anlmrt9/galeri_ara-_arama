"""Streamlit arayüzü duman testi (``streamlit.testing.v1.AppTest``) — tarayıcısız."""

from __future__ import annotations

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from otogaleri.db import Repository
from otogaleri.models import Listing


@pytest.fixture(autouse=True)
def _fresh_runtime():  # type: ignore[no-untyped-def]
    """``runtime()`` st.cache_resource ile süreç boyu önbelleklenir; her test kendi DB'sini görsün."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _app() -> AppTest:
    return AppTest.from_file("../app.py", default_timeout=60)


def test_renders_empty_state_without_errors(repo: Repository):
    at = _app().run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["🔎 Tarama", "🚗 İlanlar", "📈 Piyasa"]
    assert at.metric[0].value == "⚪ Beklemede"


def test_listings_are_rendered_and_scan_can_start_and_stop(repo: Repository):
    repo.upsert_listing(
        Listing(
            "Otoplus",
            "OP-1",
            "https://example.com/1",
            brand="Fiat",
            model="Egea",
            year=2021,
            km=10,
            price=900_000,
        )
    )
    at = _app().run()
    assert not at.exception
    assert at.dataframe[0].value.shape[0] == 1

    at.selectbox[0].select("Fiat").run()
    next(b for b in at.button if "başlat" in b.label).click().run()
    assert not at.exception
    assert "Aktif tarama" in at.info[0].value

    next(b for b in at.button if "durdur" in b.label.lower()).click().run()
    assert not at.exception
    assert at.metric[0].value == "⚪ Beklemede"
