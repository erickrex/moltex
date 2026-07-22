"""Tests for source-derived theme token CSS (workstream CSS3)."""

from __future__ import annotations

from moltex_harness.scaffold.service import BaselineService


def test_astra_palette_maps_to_moltex_colors() -> None:
    css = BaselineService._theme_token_css(
        {"--ast-global-color-0": "#123456", "--ast-global-color-1": "#abcdef"}
    )
    assert "--moltex-color-0: #123456;" in css
    assert "--moltex-color-1: #abcdef;" in css


def test_body_and_heading_fonts_are_derived_from_source() -> None:
    css = BaselineService._theme_token_css(
        {
            "--wp--preset--font-family--body": "'Source Sans 3', sans-serif",
            "--headings-font-family": "Poppins, sans-serif",
        }
    )
    assert "--moltex-body-font: 'Source Sans 3', sans-serif;" in css
    assert "--moltex-heading-font: Poppins, sans-serif;" in css


def test_unsafe_font_values_are_ignored() -> None:
    css = BaselineService._theme_token_css(
        {"--body-font-family": "x; background: url(javascript:alert(1))"}
    )
    assert "--moltex-body-font" not in css


def test_empty_tokens_produce_no_root_block() -> None:
    assert BaselineService._theme_token_css({}) == ""
