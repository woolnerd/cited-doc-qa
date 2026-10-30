"""Regression tests for the frontend brand copy, lost once in the eta consolidation."""

from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def test_sidebar_brand_shows_product_and_company():
    html = INDEX_HTML.read_text()

    assert '<span class="brand-name">Operational Knowledge Hub</span>' in html
    assert '<span class="brand-tag">Powered by Freetime AI</span>' in html


def test_page_title_matches_brand():
    html = INDEX_HTML.read_text()

    assert "<title>Operational Knowledge Hub — Freetime AI</title>" in html


def test_company_name_uses_freetime_casing():
    assert "FreeTime" not in INDEX_HTML.read_text()


def test_favicon_is_the_freetime_icon():
    """Same favicon.ico as getfreetime.ai, so the tab matches the main site."""
    html = INDEX_HTML.read_text()
    favicon = INDEX_HTML.parent / "favicon.ico"

    assert '<link rel="icon" type="image/x-icon" href="favicon.ico">' in html
    assert favicon.read_bytes()[:4] == b"\x00\x00\x01\x00"  # ICO header
