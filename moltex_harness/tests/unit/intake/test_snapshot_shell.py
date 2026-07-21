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
    }


def test_snapshot_shell_ignores_unrelated_images_and_scripts() -> None:
    result = parse_snapshot_shell(
        '<script>bad()</script><img src="hero.jpg"><a href="/contact/">Contact</a>'
    )

    assert result == {"media": [], "header_ctas": []}
