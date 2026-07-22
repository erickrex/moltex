from __future__ import annotations

from pathlib import Path

import pytest

from moltex_harness.conversion import (
    BlockConverterRegistry,
    BlockConverterSpec,
    ContentConverter,
    ShortcodeConverter,
    UrlRewriter,
)


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


def test_block_converter_registry_has_explicit_unknown_fallbacks() -> None:
    registry = BlockConverterRegistry(
        (BlockConverterSpec("vendor/card", "spectra", "converted"),)
    )

    assert registry.resolve("vendor/card", self_closing=True).disposition == "converted"
    assert registry.resolve("vendor/unknown", self_closing=False).disposition == "preserved"
    assert registry.resolve("vendor/unknown", self_closing=True).disposition == "unsupported"


def test_block_converter_registry_rejects_duplicate_or_unqualified_names() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        BlockConverterRegistry(
            (
                BlockConverterSpec("vendor/card", "spectra", "converted"),
                BlockConverterSpec("vendor/card", "spectra", "converted"),
            )
        )
    with pytest.raises(ValueError, match="namespaced"):
        BlockConverterRegistry(
            (BlockConverterSpec("card", "spectra", "converted"),)
        )

def test_shortcode_parser_preserves_nested_and_unknown_content_visibly() -> None:
    result = ShortcodeConverter().convert(
        "[caption]Photo [mystery x='[safe]']kept[/mystery][/caption]", "content:1"
    )

    assert "wp-caption" in result.html
    assert "kept" in result.html
    assert "moltex-placeholder" in result.html


def test_referenced_orphan_shortcode_placeholder_carries_stable_contract_ids() -> None:
    result = ShortcodeConverter(
        {
            "legacy_widget": {
                "evidence_id": "legacy:shortcode:fixture",
                "capability_id": "capability:legacy:fixture",
                "decision_id": "decision:legacy:fixture",
            }
        }
    ).convert("[legacy_widget color='blue']", "record:fixture")

    assert 'role="status"' in result.html
    assert 'data-moltex-evidence="legacy:shortcode:fixture"' in result.html
    assert 'data-moltex-capability="capability:legacy:fixture"' in result.html
    assert 'data-moltex-decision="decision:legacy:fixture"' in result.html
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


def test_html_forms_are_preserved_and_neutralized() -> None:
    result = ShortcodeConverter().convert(
        "<form action='/send' onsubmit='steal()'>"
        "<label>Email <input type='email' name='email' value='secret'></label>"
        "<button type='submit'>Send</button>"
        "Your message</form><p>[[gallery]]</p>",
        "content:contact",
    )

    # The visual structure and labels are preserved.
    assert '<form class="moltex-form" data-moltex-form="static"' in result.html
    assert "Your message" in result.html
    assert 'name="email"' in result.html
    assert "Send" in result.html
    # Submission behavior is stripped and cannot fire.
    assert "onsubmit" not in result.html
    assert "action" not in result.html
    assert "steal" not in result.html
    assert "secret" not in result.html
    assert 'type="button"' in result.html
    # Escaped shortcodes remain literal, and the form is reported as preserved.
    assert "[gallery]" in result.html
    assert not any(item.name == "gallery" for item in result.dispositions)
    assert any(item.code == "form_preserved" for item in result.findings)


def test_sureforms_shortcode_renders_a_safe_native_form() -> None:
    result = ShortcodeConverter().convert(
        "[sureforms id='2026']", "content:contact"
    )

    assert 'data-shortcode="form"' in result.html
    assert '<input type="email"' in result.html
    assert "Comment or Message" in result.html
    assert result.dispositions[0].name == "sureforms"
    assert result.dispositions[0].disposition == "converted"
    assert result.findings == ()


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
                '<img src="placeholder-image.jpg" alt="Template placeholder">'
            )
        }
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "https://old.example" not in receipt.sanitized_html
    assert "placeholder-image.jpg" not in receipt.sanitized_html
    assert "/media/local.png 2x" in receipt.sanitized_html
    assert 'class="moltex-media-placeholder"' in receipt.sanitized_html
    assert 'aria-label="Template placeholder"' in receipt.sanitized_html
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


def test_converter_preserves_native_gutenberg_layout_and_spectra_content(
    golden_contracts,
) -> None:
    source = """
<!-- wp:group {"layout":{"type":"constrained"},"style":{"spacing":{"padding":{"top":"2rem"}}}} -->
<div class="wp-block-group">
<!-- wp:columns {"style":{"spacing":{"blockGap":"2rem"}}} -->
<div class="wp-block-columns"><div class="wp-block-column">
<!-- wp:spectra/content {"tagName":"h1","text":"A preserved &amp; safe heading","textColor":"#ffffff","style":{"typography":{"fontSize":"2.5rem","textAlign":"center"}}} /-->
<!-- wp:paragraph --><p>Native paragraph copy.</p><!-- /wp:paragraph -->
</div></div><!-- /wp:columns -->
</div><!-- /wp:group -->
"""
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": source}
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {}),
        {"block:spectra/content": {"decision_id": "old-decision"}},
    ).convert(record)

    assert "A preserved &amp; safe heading" in receipt.sanitized_html
    assert "&amp;amp;" not in receipt.sanitized_html
    assert "Native paragraph copy." in receipt.sanitized_html
    assert "moltex-core-group" in receipt.sanitized_html
    assert "moltex-core-columns" in receipt.sanitized_html
    assert "--moltex-font-size:2.5rem" in receipt.sanitized_html
    assert "--moltex-text-align:center" in receipt.sanitized_html
    assert "--moltex-font-weight:700" not in receipt.sanitized_html
    assert "moltex-placeholder" not in receipt.sanitized_html
    assert any(item.code == "gutenberg_blocks_converted" for item in receipt.findings)


def test_converter_preserves_safe_inline_markup_in_spectra_text(
    golden_contracts,
) -> None:
    source = (
        '<!-- wp:spectra/content {"tagName":"h1","text":'
        '"Start <strong><u>learning</u></strong> safely '
        '<script>bad()</script>"} /-->'
    )
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": source}
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "<strong><u>learning</u></strong>" in receipt.sanitized_html
    assert "<script>" not in receipt.sanitized_html
    assert "bad()" not in receipt.sanitized_html


def test_converter_localizes_spectra_layout_background_and_button(
    golden_contracts,
) -> None:
    origin = golden_contracts.site_spec.source_origin
    source_image = f"{origin}/wp-content/hero.png"
    source = f'''<!-- wp:spectra/container {{"layout":{{"type":"grid","columnCount":2}},"overlayType":"image","overlayImage":{{"url":"{source_image}"}},"responsiveControls":{{"sm":{{"layout":{{"type":"grid","columnCount":1}}}}}}}} -->
<!-- wp:spectra/button {{"text":"Contact us","linkURL":"{origin}/contact/"}} /-->
<!-- /wp:spectra/container -->'''
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": source}
    )
    receipt = ContentConverter(
        UrlRewriter(
            origin,
            {f"{origin}/contact/": "/contact/"},
            {source_image: "/media/hero.png"},
        ),
        {
            "block:spectra/container": {"decision_id": "obsolete"},
            "block:spectra/button": {"decision_id": "obsolete"},
        },
    ).convert(record)

    assert "--moltex-grid-columns:repeat(2,minmax(0,1fr))" in receipt.sanitized_html
    assert "--moltex-sm-grid-columns:repeat(1,minmax(0,1fr))" in receipt.sanitized_html
    assert "/media/hero.png" in receipt.sanitized_html
    assert 'href="/contact/"' in receipt.sanitized_html
    assert receipt.rewritten_urls == 2


def test_converter_localizes_spectra_background_media(golden_contracts) -> None:
    origin = golden_contracts.site_spec.source_origin
    source_image = f"{origin}/wp-content/uploads/hero.jpg"
    source = (
        '<!-- wp:spectra/container {"backgroundColor":"rgba(0,0,0,0.5)","background":{"type":"image","media":'
        f'{{"url":"{source_image}"}},"backgroundSize":"cover",'
        '"backgroundPosition":{"x":0.48,"y":0}}} /-->'
    )
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": source}
    )

    receipt = ContentConverter(
        UrlRewriter(origin, {}, {source_image: "/media/hero.jpg"})
    ).convert(record)

    assert 'url(&quot;/media/hero.jpg&quot;)' in receipt.sanitized_html
    assert "--moltex-background-position:48% 0%" in receipt.sanitized_html
    assert "--moltex-background-blend-mode:multiply" in receipt.sanitized_html


def test_converter_keeps_dynamic_core_blocks_explicit(golden_contracts) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": '<!-- wp:latest-posts {"postsToShow":3} /-->'}
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert 'data-moltex-dynamic-block="core/latest-posts"' in receipt.sanitized_html
    assert "Latest Posts" in receipt.sanitized_html
    assert any(item.code == "gutenberg_blocks_unresolved" for item in receipt.findings)


def test_converter_renders_spectra_icon_as_local_svg_class(golden_contracts) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/icon {"icon":"circle-arrow-down"} /-->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    # The alias maps to a registered icon rendered via a CSS mask class, not a
    # text glyph or bullet.
    assert "moltex-icon--arrow-down" in receipt.sanitized_html
    assert "\u2193" not in receipt.sanitized_html
    assert "\u2022" not in receipt.sanitized_html


def test_shortcode_parser_leaves_punctuation_brackets_as_text() -> None:
    result = ShortcodeConverter().convert(
        '<a href="#">[+]</a><p>Price range: [$]</p>',
        "content:teachers",
    )

    assert '<a href="#">[+]</a>' in result.html
    assert "[$]" in result.html
    assert result.dispositions == ()
    assert result.findings == ()


def test_converter_renders_spectra_separator_without_placeholder(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/separator {"style":{"border":{"width":"3px",'
                '"style":"solid","color":"#123456"}},"width":"60%"} /-->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert '<hr class="moltex-block moltex-separator"' in receipt.sanitized_html
    assert "WordPress block requires replacement" not in receipt.sanitized_html
    assert "--moltex-border-width:3px" in receipt.sanitized_html
    assert receipt.blocks[0].name == "spectra/separator"
    assert receipt.blocks[0].disposition == "converted"


def test_converter_renders_spectra_accordion_as_native_details(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/accordion -->'
                '<!-- wp:spectra/accordion-child-item -->'
                '<!-- wp:spectra/accordion-child-header -->'
                '<!-- wp:spectra/accordion-child-header-icon /-->'
                '<!-- wp:spectra/accordion-child-header-content '
                '{"text":"<strong>Emergency service</strong>"} /-->'
                '<!-- /wp:spectra/accordion-child-header -->'
                '<!-- wp:spectra/accordion-child-details -->'
                '<p>Available now.</p>'
                '<!-- /wp:spectra/accordion-child-details -->'
                '<!-- /wp:spectra/accordion-child-item -->'
                '<!-- /wp:spectra/accordion -->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert '<details class="moltex-block moltex-accordion__item">' in receipt.sanitized_html
    assert "Emergency service" in receipt.sanitized_html
    assert "WordPress block requires replacement" not in receipt.sanitized_html
    assert all(item.disposition == "converted" for item in receipt.blocks)


def test_converter_renders_spectra_map_as_safe_external_link(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/google-map {"address":"London Eye, London",'
                '"height":"500px"} /-->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert 'class="moltex-block moltex-map"' in receipt.sanitized_html
    assert "google.com/maps/search" in receipt.sanitized_html
    assert "WordPress block requires replacement" not in receipt.sanitized_html


def test_constrained_layout_preserves_width_without_becoming_flex(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/container {"layout":{"type":"constrained",'
                '"justifyContent":"center","contentSize":"720px",'
                '"wideSize":"1100px"}} -->'
                '<!-- wp:spectra/content {"tagName":"h1","text":"Readable hero"} /-->'
                '<!-- /wp:spectra/container -->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "--moltex-display:flex" not in receipt.sanitized_html
    assert "--moltex-max-width:720px" in receipt.sanitized_html
    assert "--moltex-wide-width:1100px" in receipt.sanitized_html
    assert "--moltex-font-size" not in receipt.sanitized_html


def test_unknown_self_closing_block_is_never_silently_dropped(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={"original_html": '<!-- wp:vendor/interactive-map {"zoom":8} /-->'}
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "WordPress block requires replacement: vendor/interactive-map" in receipt.sanitized_html
    assert receipt.blocks[0].disposition == "unsupported"
    assert any(item.code == "gutenberg_blocks_unresolved" for item in receipt.findings)


def test_shared_style_compiler_accepts_safe_gradients_radii_and_shadows(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/container {"advBgGradient":"linear-gradient(90deg,#123456 0%,#abcdef 100%)","dimRatio":35,'
                '"boxShadow":"0px 8px 20px rgba(0,0,0,0.25)","style":{"border":{"radius":'
                '{"topLeft":"4px","topRight":"8px","bottomRight":"12px","bottomLeft":"16px"}}}} /-->'
            )
        }
    )

    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "linear-gradient(90deg,#123456 0%,#abcdef 100%)" in receipt.sanitized_html
    assert "--moltex-background-gradient:" in receipt.sanitized_html
    assert "--moltex-box-shadow:0px 8px 20px rgba(0,0,0,0.25)" in receipt.sanitized_html
    assert "--moltex-border-top-left-radius:4px" in receipt.sanitized_html
    assert "--moltex-overlay-opacity:0.35" in receipt.sanitized_html
    assert "--moltex-background-color:rgba(0,0,0,0.35)" not in receipt.sanitized_html


def test_shared_style_compiler_maps_wordpress_color_variables_inside_gradients(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/container {"advBgGradient":"linear-gradient(90deg,var(--ast-global-color-0) 0%,var(--ast-global-color-5) 100%)"} -->'
                "<p>Gradient content</p>"
                "<!-- /wp:spectra/container -->"
            )
        }
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(
        record
    )

    assert "linear-gradient(90deg,var(--moltex-color-0) 0%,var(--moltex-color-5) 100%)" in receipt.sanitized_html


def test_shared_style_compiler_preserves_gradient_and_image_overlay(
    golden_contracts,
) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/container {"advBgGradient":"linear-gradient(0deg,#4a4f5d 0%,#2b2e37 100%)",'
                '"dimRatio":100,"overlayType":"image","overlayImage":{"url":"https://source.example.test/wp-content/quote.png"},'
                '"overlayOpacity":19,"overlaySize":"auto","overlayPosition":{"x":1,"y":0}} /-->'
            )
        }
    )
    receipt = ContentConverter(
        UrlRewriter(
            golden_contracts.site_spec.source_origin,
            {},
            {"https://source.example.test/wp-content/quote.png": "/media/quote.png"},
        )
    ).convert(record)

    assert "--moltex-background-gradient:linear-gradient" in receipt.sanitized_html
    assert '--moltex-background-image:url(&quot;/media/quote.png&quot;)' in receipt.sanitized_html
    assert "--moltex-overlay-opacity:0.19" in receipt.sanitized_html
    assert "--moltex-background-position:100% 0%" in receipt.sanitized_html


def test_generated_gutenberg_styles_reject_css_injection(golden_contracts) -> None:
    record = golden_contracts.content_records[0].model_copy(
        update={
            "original_html": (
                '<!-- wp:spectra/content {"tagName":"h2","text":"Safe",'
                '"textColor":"red;position:fixed","style":{"spacing":{"padding":'
                '{"top":"1rem;background:url(javascript:alert(1))"}}}} /-->'
            )
        }
    )
    receipt = ContentConverter(
        UrlRewriter(golden_contracts.site_spec.source_origin, {}, {})
    ).convert(record)

    assert "Safe" in receipt.sanitized_html
    assert "javascript" not in receipt.sanitized_html
    assert "position:fixed" not in receipt.sanitized_html


def test_preserved_form_keeps_select_and_neutralizes_submit_input() -> None:
    result = ShortcodeConverter().convert(
        "<form>"
        "<select name='topic'><option value='a'>Support</option>"
        "<option value='b' selected>Sales</option></select>"
        "<input type='submit' value='Go'>"
        "</form>",
        "content:contact",
    )

    assert "<select" in result.html
    assert "Support" in result.html
    assert "Sales" in result.html
    # The submit input is downgraded to an inert button and its value dropped.
    assert 'type="button"' in result.html
    assert 'type="submit"' not in result.html
    assert "Go" not in result.html
