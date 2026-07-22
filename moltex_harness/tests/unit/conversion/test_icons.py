"""Tests for the local SVG icon registry and Gutenberg icon rendering."""

from __future__ import annotations

from moltex_harness.conversion.gutenberg import GutenbergRenderer
from moltex_harness.conversion.icons import icon_mask_css, known_icon_slug


def _render(source: str) -> object:
    return GutenbergRenderer(lambda url: (url, False), {}).render(source)


def test_known_icon_slug_validates_against_registry() -> None:
    assert known_icon_slug("leaf") == "leaf"
    assert known_icon_slug("CALENDAR-DAYS") == "calendar-days"
    assert known_icon_slug("definitely-not-an-icon") is None
    assert known_icon_slug("../evil") is None


def test_atomic_wind_icon_renders_local_svg_class_not_a_bullet() -> None:
    result = _render(
        '<!-- wp:atomic-wind/icon {"icon":"leaf"} /-->'
    )
    assert 'class="moltex-block moltex-icon moltex-icon--leaf"' in result.html
    assert "\u2022" not in result.html  # no bullet
    assert "\u2713" not in result.html  # no check glyph
    assert result.unknown_icons == ()


def test_spectra_icon_alias_maps_to_registered_icon() -> None:
    result = _render('<!-- wp:spectra/icon {"icon":"calendar"} /-->')
    assert "moltex-icon--calendar-days" in result.html


def test_unknown_icon_uses_fallback_and_is_reported() -> None:
    result = _render('<!-- wp:atomic-wind/icon {"icon":"unicorn"} /-->')
    assert "moltex-icon--unknown" in result.html
    assert result.unknown_icons == ("unicorn",)


def test_icon_mask_css_contains_registry_and_fallback_masks() -> None:
    css = icon_mask_css()
    assert ".moltex-icon {" in css
    assert ".moltex-icon--leaf {" in css
    assert ".moltex-icon--unknown {" in css
    assert "mask-image" in css
    # Data URIs are self-contained; no external network references.
    assert "http://" not in css.replace("http://www.w3.org/2000/svg", "")
