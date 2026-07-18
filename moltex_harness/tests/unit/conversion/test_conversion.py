from __future__ import annotations

from pathlib import Path

from moltex_harness.conversion import ContentConverter, ShortcodeConverter, UrlRewriter


def test_url_rewriter_handles_media_fragments_srcset_and_is_idempotent() -> None:
    rewriter = UrlRewriter(
        "https://old.test",
        {"https://old.test/about/": "/about/"},
        {"https://old.test/wp-content/a.jpg": "/media/a.jpg"},
    )

    assert rewriter.rewrite("https://old.test/about/#team") == ("/about/#team", True)
    assert rewriter.rewrite("/media/a.jpg") == ("/media/a.jpg", False)
    assert rewriter.rewrite_srcset("https://old.test/wp-content/a.jpg 1x, /media/a.jpg 2x") == (
        "/media/a.jpg 1x, /media/a.jpg 2x",
        1,
    )


def test_shortcode_parser_preserves_nested_and_unknown_content_visibly() -> None:
    result = ShortcodeConverter().convert(
        "[caption]Photo [mystery x='[safe]']kept[/mystery][/caption]", "content:1"
    )

    assert "wp-caption" in result.html
    assert "kept" in result.html
    assert "moltex-placeholder" in result.html
    assert any(item.code == "unknown_shortcode_preserved" for item in result.findings)


def test_converter_removes_active_content_and_rewrites_local_media(golden_contracts) -> None:
    record = golden_contracts.content_records[0]
    hostile = record.model_copy(
        update={"original_html": (
            '<script>alert(1)</script><p onclick="bad()">Safe text</p>'
            '<img src="http://localhost:8094/wp-content/uploads/2026/07/lakeside-pavilion.png">'
        )},
    )
    converter = ContentConverter(
        UrlRewriter(
            golden_contracts.site_spec.source_origin,
            {item.source_url: item.target_url for item in golden_contracts.url_map},
            {item.source_url: item.target_url for item in golden_contracts.media_map},
        )
    )

    receipt = converter.convert(hostile)

    assert "script" not in receipt.sanitized_html
    assert "onclick" not in receipt.sanitized_html
    assert "Safe text" in receipt.sanitized_html
    assert "/media/" in receipt.sanitized_html
    assert receipt.rewritten_urls == 1


def test_gutenberg_comments_and_attributes_are_not_parsed_as_shortcodes() -> None:
    source = (
        Path(__file__).parents[2]
        / "fixtures/conversion/gutenberg-kadence-contact.html"
    ).read_text(encoding="utf-8")

    result = ShortcodeConverter().convert(source, "content:page:77")

    assert result.html.strip() == '<div class="wp-block-kadence-rowlayout" data-config="[also-not-a-shortcode]"><p>Visible copy</p></div>'
    assert result.dispositions == ()
    assert result.findings == ()


def test_html_forms_are_replaced_and_escaped_shortcodes_remain_literal() -> None:
    result = ShortcodeConverter().convert(
        "<form><input value='secret'>Do not retain</form><p>[[gallery]]</p>",
        "content:contact",
    )

    assert "Do not retain" not in result.html
    assert "Form requires integration" in result.html
    assert "[gallery]" in result.html
    assert not any(item.name == "gallery" for item in result.dispositions)
    assert any(item.code == "form_placeholder" for item in result.findings)


def test_complex_content_fallback_is_explicitly_reported(golden_contracts) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": "<table><tr><td>Preserved</td></tr></table>"}
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert receipt.body_format == "sanitized_html"
    assert any(
        item.code == "conversion_fallback"
        and item.context["reason"] == "complex_structure"
        for item in receipt.findings
    )


def test_unmapped_remote_media_is_removed_from_local_only_baseline(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<img src="https://old.example/plugin-placeholder.png" '
                'srcset="https://old.example/a.png 1x, /media/local.png 2x">'
            )
        }
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "https://old.example" not in receipt.sanitized_html
    assert "/media/local.png 2x" in receipt.sanitized_html
    assert any(item.code == "unmapped_media_removed" for item in receipt.findings)


def test_large_content_fallback_is_explicitly_reported(golden_contracts) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": "<p>" + ("editable " * 13_000) + "</p>"}
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert receipt.body_format == "sanitized_html"
    assert any(
        item.code == "conversion_fallback"
        and item.context["reason"] == "large_content"
        for item in receipt.findings
    )
