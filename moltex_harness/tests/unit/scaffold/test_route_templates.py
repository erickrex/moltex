"""Tests for generated route templates (workstream CSS7)."""

from __future__ import annotations

from pathlib import Path

from moltex_harness.scaffold.service import BaselineService


def test_listing_route_is_listing_first_with_featured_media(tmp_path: Path) -> None:
    BaselineService._write_route_templates(tmp_path)
    listing = (
        tmp_path / "src" / "components" / "routes" / "ListingRoute.astro"
    ).read_text(encoding="utf-8")

    # The post-card grid renders before the optional page intro content, so a
    # generic page hero can no longer appear ahead of the listing.
    assert "listing-grid" in listing
    assert "listing-intro" in listing
    assert listing.index("listing-grid") < listing.index("listing-intro")
    # Cards carry featured media and publication metadata.
    assert "listing-card__media" in listing
    assert "item.media[0].src" in listing
    assert "<time datetime={item.publishedAt}>" in listing
