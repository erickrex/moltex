"""Local, dependency-free SVG icon registry (workstream CSS5).

Gutenberg icon blocks previously collapsed to a bullet or check glyph, which is
visually and semantically wrong. This module provides a bounded set of approved
icons rendered as CSS ``mask-image`` data URIs. Icons are emitted in HTML as a
semantic ``<span class="moltex-icon moltex-icon--NAME">`` and colored with
``currentColor``; the actual shape lives in generated CSS so it survives HTML
sanitization and never depends on a plugin runtime or a CDN.

Unknown icon names resolve to a neutral fallback and are reported, never
silently replaced with an unrelated glyph.
"""

from __future__ import annotations

import re
import urllib.parse

_ICON_SLUG = re.compile(r"[a-z0-9-]{1,40}")

# Approved icons as filled 24x24 silhouettes. Path data is authored locally; no
# untrusted input is ever interpolated into these values.
ICON_REGISTRY: dict[str, str] = {
    "check": "M9.55 17.6 4.4 12.45l1.4-1.4 3.75 3.75 8.25-8.25 1.4 1.4z",
    "check-circle": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m-1.1 14.2-3.9-3.9 1.4-1.4 2.5 2.5 5-5 1.4 1.4z",
    "arrow-right": "M13 5l7 7-7 7-1.4-1.4 4.6-4.6H4v-2h12.2L11.6 6.4z",
    "arrow-down": "M11 4v12.2l-4.6-4.6L5 13l7 7 7-7-1.4-1.4-4.6 4.6V4z",
    "plus": "M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z",
    "plus-circle": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 11h4v-2h-4V7h-2v4H7v2h4v4h2z",
    "star": "M12 2l2.9 6.2 6.6.7-4.9 4.4 1.4 6.5L12 17.9 5.9 20.2l1.4-6.5L2.4 9.3l6.6-.7z",
    "heart": "M12 21 4.5 13.5a5 5 0 0 1 7-7l.5.5.5-.5a5 5 0 0 1 7 7z",
    "leaf": "M4 20c0-8 6-14 16-14 0 10-6 16-14 16 0-4 2-7 6-9-3 1-6 3-8 7z",
    "map-pin": "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7m0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z",
    "phone": "M6.6 3H4a2 2 0 0 0-2 2 16 16 0 0 0 15 15 2 2 0 0 0 2-2v-2.6a1 1 0 0 0-.8-1l-3-.6a1 1 0 0 0-1 .3l-1.2 1.2a12 12 0 0 1-5-5l1.2-1.2a1 1 0 0 0 .3-1l-.6-3a1 1 0 0 0-1-.8z",
    "calendar-days": "M7 2v2H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2zm-2 7h14v10H5zm2 2v2h2v-2zm4 0v2h2v-2zm4 0v2h2v-2z",
    "book-open": "M12 5c-2-1.3-4.5-2-7-2H3v15h2c2.5 0 5 .7 7 2 2-1.3 4.5-2 7-2h2V3h-2c-2.5 0-5 .7-7 2zm0 2v11c-1.8-1-3.9-1.5-6-1.6V5.4c2.1.1 4.2.6 6 1.6z",
    "users": "M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7m8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6M2 19c0-3 3-5 6-5s6 2 6 5v1H2zm14.5-4c2 .4 3.5 2 3.5 4v1h-4v-1c0-1.6-.6-3-1.6-4z",
    "quote": "M7 7H4v6h3l-1 4h2l2-4V7zm10 0h-3v6h3l-1 4h2l2-4V7z",
    "clock": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 10V6h-2v7h6v-2z",
}

_FALLBACK_PATH = "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16m0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12"


def known_icon_slug(raw_name: str) -> str | None:
    """Return the validated registry slug for ``raw_name`` or ``None``."""

    slug = str(raw_name).strip().casefold()
    if _ICON_SLUG.fullmatch(slug) and slug in ICON_REGISTRY:
        return slug
    return None


def _data_uri(path_d: str) -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
        f"<path d='{path_d}' fill='black'/></svg>"
    )
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe="")


def icon_mask_css() -> str:
    """Generate the base icon rule plus one mask rule per registered icon."""

    lines = [
        "",
        "/* Local SVG icon registry rendered via CSS masks (no runtime deps). */",
        ".moltex-icon { display: inline-block; width: 1em; height: 1em; "
        "vertical-align: -0.125em; background-color: currentColor; "
        "-webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; "
        "-webkit-mask-position: center; mask-position: center; "
        "-webkit-mask-size: contain; mask-size: contain; }",
    ]
    entries = {**ICON_REGISTRY, "unknown": _FALLBACK_PATH}
    for name in sorted(entries):
        uri = _data_uri(entries[name])
        lines.append(
            f'.moltex-icon--{name} {{ -webkit-mask-image: url("{uri}"); '
            f'mask-image: url("{uri}"); }}'
        )
    return "\n".join(lines) + "\n"
