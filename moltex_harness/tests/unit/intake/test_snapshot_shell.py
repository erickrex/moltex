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
        "text": "Example Company Privacy",
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
