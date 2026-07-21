from __future__ import annotations

import json
import xml.etree.ElementTree as ET

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
