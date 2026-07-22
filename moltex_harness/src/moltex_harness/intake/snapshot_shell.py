"""Extract bounded global-shell observations from an untrusted HTML snapshot.

Shell recognition is theme-independent: it relies on semantic landmarks
(``header``, ``footer``, anchors, images) and common logo/button class families
shared across WordPress themes such as Astra and Neve, rather than one theme's
selectors. Text is repaired for common UTF-8 mojibake before it is returned.
"""

from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Any

# Class families that identify a site logo image across common themes.
_LOGO_CLASSES = {
    "custom-logo",
    "neve-site-logo",
    "site-logo",
    "site-logo-img",
    "logo",
    "brand-logo",
    "navbar-brand-img",
}
# Anchors that wrap a logo image (the logo class may live on the link).
_BRAND_ANCHOR_CLASSES = {
    "custom-logo-link",
    "neve-site-logo",
    "site-logo",
    "logo",
    "brand",
    "navbar-brand",
    "site-branding",
    "site-title",
}
# Class families that identify a header call-to-action button across themes.
_BUTTON_CLASSES = {
    "ast-custom-button-link",
    "button-primary",
    "btn-primary",
    "wp-block-button__link",
    "header-button",
    "nv-nav-cta",
    "hfg-button",
    "menu-item-button",
}
# Generic button classes only count as a CTA inside the header landmark.
_GENERIC_BUTTON_CLASSES = {"button", "btn", "cta"}

_MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "\ufffd", " Â")


def repair_mojibake(text: str) -> str:
    """Repair common UTF-8-as-Latin-1/CP1252 mojibake in shell text.

    The repair is conditional: it only runs when a known mojibake marker is
    present, and the result is accepted only when it decodes to clean UTF-8 with
    no replacement characters and no remaining markers. This avoids an
    unconditional character-set round trip that could corrupt valid text.
    """

    if not text or not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text
    for encoding in ("cp1252", "latin-1"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if "\ufffd" in repaired:
            continue
        if any(marker in repaired for marker in _MOJIBAKE_MARKERS):
            continue
        return repaired
    return text


class _SnapshotShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.logo: dict[str, str] | None = None
        self.ctas: list[dict[str, str]] = []
        self._cta: dict[str, str] | None = None
        self._cta_text: list[str] = []
        self._style_depth = 0
        self.style_parts: list[str] = []
        self._footer_depth = 0
        self.footer_text: list[str] = []
        self.footer_links: list[dict[str, str]] = []
        self._footer_link: dict[str, str] | None = None
        self._footer_link_text: list[str] = []
        self._notice_depth = 0
        self.header_notice: list[str] = []
        self.header_overlay = False
        self._header_depth = 0
        self._brand_anchor = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        classes = set(values.get("class", "").split())
        rel = set(values.get("rel", "").split())
        role = values.get("role", "").strip().casefold()
        normalized_tag = tag.casefold()

        if normalized_tag == "body":
            self.header_overlay = "ast-theme-transparent-header" in classes
        if normalized_tag == "header":
            self._header_depth += 1
        if self._notice_depth:
            self._notice_depth += 1
        elif normalized_tag == "div" and "ast-builder-html-element" in classes:
            self._notice_depth = 1
        if normalized_tag == "style":
            self._style_depth += 1
        if normalized_tag == "footer":
            self._footer_depth += 1

        if normalized_tag == "a":
            href = values.get("href", "#").strip() or "#"
            if "home" in rel or (classes & _BRAND_ANCHOR_CLASSES):
                self._brand_anchor = True
            is_cta = bool(classes & _BUTTON_CLASSES) or role == "button"
            if not is_cta and self._header_depth:
                is_cta = bool(classes & _GENERIC_BUTTON_CLASSES)
            if is_cta and self._cta is None:
                self._cta = {"url": href}
                self._cta_text = []

        if normalized_tag == "img" and self.logo is None:
            source = values.get("src", "").strip()
            if source and (classes & _LOGO_CLASSES or self._brand_anchor):
                self.logo = {
                    "url": source,
                    "alt": values.get("alt", "").strip(),
                    "role": "site-logo",
                }

        if normalized_tag == "a" and self._footer_depth:
            href = values.get("href", "").strip()
            if href:
                self._footer_link = {"url": href}
                self._footer_link_text = []

    def handle_data(self, data: str) -> None:
        if self._style_depth and sum(map(len, self.style_parts)) < 262_144:
            self.style_parts.append(data)
        if self._footer_depth:
            if self._footer_link is not None:
                self._footer_link_text.append(data)
            else:
                self.footer_text.append(data)
        if self._cta is not None:
            self._cta_text.append(data)
        if self._notice_depth and self._cta is None:
            self.header_notice.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if self._notice_depth:
            self._notice_depth -= 1
        if normalized_tag == "style" and self._style_depth:
            self._style_depth -= 1
        if normalized_tag == "header" and self._header_depth:
            self._header_depth -= 1
        if normalized_tag == "a":
            self._brand_anchor = False
            if self._footer_link is not None:
                label = " ".join("".join(self._footer_link_text).split())
                if label:
                    self.footer_links.append({**self._footer_link, "label": label})
                self._footer_link = None
                self._footer_link_text = []
            if self._cta is not None:
                label = " ".join("".join(self._cta_text).split())
                if label:
                    self.ctas.append({**self._cta, "label": label})
                self._cta = None
                self._cta_text = []
        if normalized_tag == "footer" and self._footer_depth:
            self._footer_depth -= 1


_THEME_TOKEN = re.compile(
    r"(?P<name>--[a-zA-Z0-9_-]{1,100})\s*:\s*"
    r"(?P<value>[a-zA-Z0-9#(),.%\s'\"/_-]{1,200})\s*;"
)


def _theme_tokens(styles: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _THEME_TOKEN.finditer(styles):
        name = match.group("name")
        value = " ".join(match.group("value").split())
        lowered = value.casefold()
        if any(unsafe in lowered for unsafe in ("url(", "expression", "javascript")):
            continue
        values[name] = value
    return dict(sorted(values.items()))


def parse_snapshot_shell(value: str) -> dict[str, Any]:
    parser = _SnapshotShellParser()
    parser.feed(value)
    footer_text: list[str] = []
    seen_text: set[str] = set()
    for part in parser.footer_text:
        normalized = repair_mojibake(" ".join(part.split()))
        if normalized and normalized not in seen_text:
            footer_text.append(normalized)
            seen_text.add(normalized)
    footer_links: list[dict[str, str]] = []
    seen_links: set[tuple[str, str]] = set()
    for link in parser.footer_links:
        label = repair_mojibake(link["label"])
        key = (link["url"], label)
        if key not in seen_links:
            footer_links.append({"url": link["url"], "label": label})
            seen_links.add(key)
    logo = None
    if parser.logo:
        logo = {**parser.logo, "alt": repair_mojibake(parser.logo.get("alt", ""))}
    ctas = [
        {"url": cta["url"], "label": repair_mojibake(cta["label"])}
        for cta in parser.ctas[:1]
    ]
    return {
        "media": [logo] if logo else [],
        "header_ctas": ctas,
        "header_notice": repair_mojibake(
            " ".join(" ".join(parser.header_notice).split())[:200]
        ),
        "header_overlay": parser.header_overlay,
        "theme_tokens": _theme_tokens("".join(parser.style_parts)),
        "footer": {
            "text": " ".join(footer_text)[:1000],
            "links": footer_links[:24],
        },
    }
