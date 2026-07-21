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
    assert "{site.siteName}" in layout
    assert site == {"siteName": hostile}
    styles = (tmp_path / "src/styles/moltex.css").read_text(encoding="utf-8")
    assert "--moltex-color-0: #0f57fb" in styles
    assert ".moltex-block" in styles


def test_route_template_does_not_dump_media_outside_converted_content(tmp_path) -> None:
    BaselineService._write_route_templates(tmp_path)

    template = (tmp_path / "src/pages/[...path].astro").read_text(
        encoding="utf-8"
    )
    assert "record.media?.map" not in template
    assert "hasRenderedH1" in template


def test_navigation_uses_largest_menu_as_primary(tmp_path) -> None:
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
        item("primary", "home", "Home", 1),
        item("primary", "services", "Services", 2),
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
    assert [entry["label"] for entry in navigation] == ["Home", "Services"]


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
