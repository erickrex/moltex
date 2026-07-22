from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from moltex_harness.scaffold import BaselineService


def test_hostile_site_name_is_data_not_astro_source(tmp_path) -> None:
    hostile = "</a><script>globalThis.pwned = true</script>"

    BaselineService._write_shell(tmp_path, hostile)

    layout = (tmp_path / "src/layouts/BaseLayout.astro").read_text(
        encoding="utf-8"
    )
    site = json.loads((tmp_path / "src/data/site.json").read_text(encoding="utf-8"))
    assert hostile not in layout
    assert "site.siteName" in layout
    assert site == {
        "siteName": hostile,
            "siteLogo": None,
            "headerCta": None,
            "headerNotice": None,
        "footer": {"text": hostile, "links": []},
    }
    styles = (tmp_path / "src/styles/moltex.css").read_text(encoding="utf-8")
    assert "--moltex-color-0: #0f57fb" in styles
    assert ".moltex-block" in styles
    assert ".moltex-block::before" in styles
    assert "--moltex-background-gradient" in styles
    assert ".site-menu__toggle" in styles
    assert 'aria-label="Main menu toggle"' in layout
    assert 'type="checkbox"' in layout
    assert layout.count("<NavigationList") == 1
    assert "<script>" not in layout


def test_shell_renders_evidence_linked_logo_and_header_cta(tmp_path) -> None:
    BaselineService._write_shell(
        tmp_path,
        "Example",
        {
            "siteLogo": {"src": "/media/logo.png", "alt": "Example logo"},
            "headerCta": {"href": "/tutors/", "label": "Find A Tutor"},
            "themeTokens": {"--ast-global-color-0": "#123456"},
            "footer": {
                "text": "Example footer",
                "links": [{"url": "/privacy/", "label": "Privacy"}],
            },
        },
    )

    site = json.loads((tmp_path / "src/data/site.json").read_text(encoding="utf-8"))
    layout = (tmp_path / "src/layouts/BaseLayout.astro").read_text(
        encoding="utf-8"
    )
    styles = (tmp_path / "src/styles/moltex.css").read_text(encoding="utf-8")
    assert site["siteLogo"]["src"] == "/media/logo.png"
    assert site["headerCta"] == {"href": "/tutors/", "label": "Find A Tutor"}
    assert "site-brand__logo" in layout
    assert "site-header__cta" in layout
    assert ".site-header__cta" in styles
    assert site["footer"]["links"][0]["label"] == "Privacy"
    assert "site-footer__inner" in layout
    assert "--moltex-color-0: #123456" in styles


def test_shell_url_rewriter_localizes_same_origin_routes() -> None:
    url_map = {"/about/": "/company/"}

    assert BaselineService._rewrite_shell_url(
        "https://example.test/about/#team",
        "https://example.test/",
        url_map,
    ) == "/company/#team"
    assert BaselineService._rewrite_shell_url(
        "https://external.test/about/",
        "https://example.test/",
        url_map,
    ) == "https://external.test/about/"


def test_shell_rebuilds_only_safe_font_faces_from_theme_evidence(tmp_path) -> None:
    rendered = tmp_path / "bundle/theme/rendered"
    rendered.mkdir(parents=True)
    (rendered / "fonts.css").write_text(
        """
        @font-face {
          font-family: 'Staatliches';
          font-style: normal;
          font-weight: 400;
          src: url(https://fonts.gstatic.com/font.ttf) format('truetype');
        }
        @font-face {
          font-family: 'Bad';
          src: url(javascript:alert(1)) format('truetype');
        }
        body { background: url(https://tracker.example/pixel); }
        """,
        encoding="utf-8",
    )

    BaselineService._write_shell(
        tmp_path / "site",
        "Example",
        source_bundle=tmp_path / "bundle",
    )

    styles = (tmp_path / "site/src/styles/moltex.css").read_text(encoding="utf-8")
    assert 'font-family: "Staatliches"' in styles
    assert "https://fonts.gstatic.com/font.ttf" in styles
    assert "javascript:" not in styles
    assert "tracker.example" not in styles


def test_route_template_does_not_dump_media_outside_converted_content(tmp_path) -> None:
    BaselineService._write_route_templates(tmp_path)

    template = (tmp_path / "src/pages/[...path].astro").read_text(
        encoding="utf-8"
    )
    page = (tmp_path / "src/components/routes/PageRoute.astro").read_text(
        encoding="utf-8"
    )
    post = (tmp_path / "src/components/routes/PostRoute.astro").read_text(
        encoding="utf-8"
    )
    assert "record.media?.map" not in template
    assert "hasRenderedHeading" in page
    assert "const featured = record.media?.[0]" in post
    assert "post-meta" in post
    assert "post-navigation" in post


def test_navigation_uses_assigned_primary_menu_over_larger_stale_menu(tmp_path) -> None:
    def item(menu_id: str, navigation_id: str, label: str, order: int):
        return SimpleNamespace(
            menu_id=menu_id,
            navigation_id=navigation_id,
            parent_navigation_id=None,
            route_contract_id=f"route:{navigation_id}",
            label=label,
            order=order,
        )

    sources = [
        item("footer", "privacy", "Privacy", 1),
        item("menu:primary:21", "home", "Home", 1),
        item("menu:primary:21", "courses", "Courses", 2),
        item("stale", "about", "About", 1),
        item("stale", "services", "Services", 2),
        item("stale", "properties", "Properties", 3),
    ]
    contracts = SimpleNamespace(
        site_spec=SimpleNamespace(global_navigation=sources)
    )
    routes = {
        source.route_contract_id: SimpleNamespace(target_url=f"/{source.navigation_id}/")
        for source in sources
    }

    BaselineService._write_navigation(tmp_path, contracts, routes, set())

    navigation = json.loads(
        (tmp_path / "src/data/navigation.json").read_text(encoding="utf-8")
    )
    assert [entry["label"] for entry in navigation] == ["Home", "Courses"]


def test_sitemap_uses_xml_serializer(golden_contracts, tmp_path) -> None:
    site_spec = golden_contracts.site_spec.model_copy(
        update={"target_canonical_origin": "https://target.example.test/?a=1&b=2"}
    )
    contracts = golden_contracts.model_copy(update={"site_spec": site_spec})

    BaselineService._write_metadata(tmp_path, contracts, set())

    sitemap = tmp_path / "public/sitemap.xml"
    raw = sitemap.read_text(encoding="utf-8")
    root = ET.parse(sitemap).getroot()
    locations = [element.text for element in root if element.tag.endswith("loc")]
    if not locations:
        locations = [
            element.text for element in root.iter() if element.tag.endswith("loc")
        ]
    assert "&amp;" in raw
    assert locations[0] is not None
    assert locations[0].startswith("https://target.example.test/?a=1&b=2")


def test_redirect_control_characters_are_rejected() -> None:
    with pytest.raises(ValueError, match="must not contain whitespace"):
        BaselineService._redirect_line("/safe\n/injected", "/target", 301)


def test_route_template_count_is_constant_for_large_route_tables(tmp_path) -> None:
    BaselineService._write_route_templates(tmp_path)

    routes = [
        {
            "routeId": f"route:{index}",
            "path": f"route-{index}",
            "recordId": f"record:{index}",
            "listingRecordIds": [],
        }
        for index in range(10_000)
    ]
    (tmp_path / "src/data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/data/routes.json").write_text(
        json.dumps(routes), encoding="utf-8"
    )

    assert len(list((tmp_path / "src/pages").glob("*.astro"))) == 2
    assert len(json.loads((tmp_path / "src/data/routes.json").read_text())) == 10_000


def test_block_support_inventory_reports_unsupported_shapes(tmp_path) -> None:
    receipts = [
        SimpleNamespace(
            record_id="content:page:1",
            blocks=(
                SimpleNamespace(
                    name="core/paragraph",
                    namespace="core",
                    attribute_signature="shape-a",
                    disposition="converted",
                    count=2,
                ),
                SimpleNamespace(
                    name="vendor/map",
                    namespace="vendor",
                    attribute_signature="shape-b",
                    disposition="unsupported",
                    count=1,
                ),
            ),
        )
    ]
    routes = [
        SimpleNamespace(
            content_record_id="content:page:1", contract_id="route:page:1"
        )
    ]

    BaselineService._write_block_inventory(tmp_path, receipts, routes)

    report = json.loads(
        (tmp_path / ".moltex/reports/block-support-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "blocked"
    assert report["counts"] == {"converted": 2, "unsupported": 1}
    assert report["entries"][1]["routeId"] == "route:page:1"


def test_body_marker_normalizes_entity_encoded_gutenberg_formatting() -> None:
    body = (
        "&amp;lt;strong&amp;gt;&amp;lt;u&amp;gt;Start&amp;lt;/u&amp;gt;"
        "&amp;lt;/strong&amp;gt; learning a new language today"
    )

    assert BaselineService._body_marker(body) == "Start learning a new language today"


def test_body_marker_keeps_inline_link_text_with_adjacent_punctuation() -> None:
    body = (
        'Welcome to <a href="https://example.test/">Astra Starter Templates</a>.'
        " This is your first post."
    )

    assert BaselineService._body_marker(body) == (
        "Welcome to Astra Starter Templates. This is your first post."
    )


def test_baseline_verifier_normalizes_tag_spacing_before_punctuation(tmp_path) -> None:
    BaselineService._write_scripts(tmp_path)
    verifier = (tmp_path / "scripts/verify-baseline.mjs").read_text(
        encoding="utf-8"
    )

    assert '.replace(/\\s+([.,;:!?])/g, "$1")' in verifier
