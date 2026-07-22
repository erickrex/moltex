from __future__ import annotations

from moltex_harness.intake.snapshot_shell import parse_snapshot_shell


def test_snapshot_shell_extracts_custom_logo_and_header_cta() -> None:
    result = parse_snapshot_shell(
        """
        <header>
          <a href="/"><img class="custom-logo" src="https://example.test/logo.png"
            alt="Language Tutors"></a>
          <a class="ast-custom-button-link" href="/tutors/">
            <span>Find A Tutor</span>
          </a>
        </header>
        """
    )

    assert result == {
        "media": [
            {
                "url": "https://example.test/logo.png",
                "alt": "Language Tutors",
                "role": "site-logo",
            }
        ],
        "header_ctas": [{"url": "/tutors/", "label": "Find A Tutor"}],
        "header_notice": "",
        "header_overlay": False,
        "theme_tokens": {},
        "footer": {"text": "", "links": []},
    }


def test_snapshot_shell_ignores_unrelated_images_and_scripts() -> None:
    result = parse_snapshot_shell(
        '<script>bad()</script><img src="hero.jpg"><a href="/contact/">Contact</a>'
    )

    assert result == {
        "media": [],
        "header_ctas": [],
        "header_notice": "",
        "header_overlay": False,
        "theme_tokens": {},
        "footer": {"text": "", "links": []},
    }


def test_snapshot_shell_extracts_safe_theme_tokens_and_footer() -> None:
    result = parse_snapshot_shell(
        """
        <style>:root {
          --ast-global-color-0: #123456;
          --wp--preset--font-family--body: 'Source Sans 3', sans-serif;
          --unsafe: url(javascript:bad);
        }</style>
        <footer><p>Example Company</p><a href="/privacy/">Privacy</a></footer>
        """
    )

    assert result["theme_tokens"] == {
        "--ast-global-color-0": "#123456",
        "--wp--preset--font-family--body": "'Source Sans 3', sans-serif",
    }
    assert result["footer"] == {
        "text": "Example Company",
        "links": [{"url": "/privacy/", "label": "Privacy"}],
    }


def test_snapshot_shell_deduplicates_responsive_footer_content() -> None:
    result = parse_snapshot_shell(
        """
        <footer>
          <p>© 2026 Example</p>
          <a href="/privacy/">Privacy</a>
          <p>© 2026 Example</p>
          <a href="/privacy/">Privacy</a>
        </footer>
        """
    )

    assert result["footer"] == {
        "text": "© 2026 Example",
        "links": [{"url": "/privacy/", "label": "Privacy"}],
    }


def test_snapshot_shell_observes_header_mode_and_notice() -> None:
    result = parse_snapshot_shell(
        '<body class="ast-theme-transparent-header">'
        '<div class="ast-builder-html-element"><h6>Always open</h6></div>'
        '</body>'
    )

    assert result["header_overlay"] is True
    assert result["header_notice"] == "Always open"


def test_snapshot_shell_extracts_neve_logo_and_generic_button_cta() -> None:
    result = parse_snapshot_shell(
        """
        <header>
          <a class="neve-site-logo" href="/">
            <img src="https://example.test/wp_finder.png" alt="WP Finder">
          </a>
          <a class="button button-primary" href="/book/">Book Appointment</a>
        </header>
        """
    )

    assert result["media"] == [
        {
            "url": "https://example.test/wp_finder.png",
            "alt": "WP Finder",
            "role": "site-logo",
        }
    ]
    assert result["header_ctas"] == [{"url": "/book/", "label": "Book Appointment"}]


def test_snapshot_shell_recognizes_logo_via_rel_home_anchor() -> None:
    result = parse_snapshot_shell(
        '<header><a rel="home" href="/">'
        '<img src="https://example.test/brand.svg" alt="Brand"></a></header>'
    )

    assert result["media"] == [
        {"url": "https://example.test/brand.svg", "alt": "Brand", "role": "site-logo"}
    ]


def test_snapshot_shell_ignores_generic_button_outside_header() -> None:
    result = parse_snapshot_shell('<a class="button" href="/x/">Read</a>')

    assert result["header_ctas"] == []


def test_snapshot_shell_repairs_footer_mojibake() -> None:
    result = parse_snapshot_shell(
        "<footer><p>\u00c2\u00a9 2026 WP Telescope</p></footer>"
    )

    assert result["footer"]["text"] == "\u00a9 2026 WP Telescope"


def test_snapshot_shell_repairs_cta_and_notice_mojibake() -> None:
    result = parse_snapshot_shell(
        '<body class="ast-theme-transparent-header">'
        '<div class="ast-builder-html-element"><span>Caf\u00c3\u00a9 hours</span></div>'
        "</body>"
    )

    assert result["header_notice"] == "Caf\u00e9 hours"
