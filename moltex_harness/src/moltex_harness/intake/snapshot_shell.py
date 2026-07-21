"""Extract bounded global-shell observations from an untrusted HTML snapshot."""

from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Any


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

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        classes = set(values.get("class", "").split())
        normalized_tag = tag.casefold()
        if normalized_tag == "body":
            self.header_overlay = "ast-theme-transparent-header" in classes
        if self._notice_depth:
            self._notice_depth += 1
        elif normalized_tag == "div" and "ast-builder-html-element" in classes:
            self._notice_depth = 1
        if normalized_tag == "style":
            self._style_depth += 1
        if normalized_tag == "footer":
            self._footer_depth += 1
        if tag.casefold() == "img" and "custom-logo" in classes and self.logo is None:
            source = values.get("src", "").strip()
            if source:
                self.logo = {
                    "url": source,
                    "alt": values.get("alt", "").strip(),
                    "role": "site-logo",
                }
        if tag.casefold() == "a" and "ast-custom-button-link" in classes:
            self._cta = {"url": values.get("href", "#").strip() or "#"}
            self._cta_text = []
        if normalized_tag == "a" and self._footer_depth:
            href = values.get("href", "").strip()
            if href:
                self._footer_link = {"url": href}
                self._footer_link_text = []

    def handle_data(self, data: str) -> None:
        if self._style_depth and sum(map(len, self.style_parts)) < 262_144:
            self.style_parts.append(data)
        if self._footer_depth:
            self.footer_text.append(data)
            if self._footer_link is not None:
                self._footer_link_text.append(data)
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
        if normalized_tag == "a":
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
    return {
        "media": [parser.logo] if parser.logo else [],
        "header_ctas": parser.ctas[:1],
        "header_notice": " ".join(" ".join(parser.header_notice).split())[:200],
        "header_overlay": parser.header_overlay,
        "theme_tokens": _theme_tokens("".join(parser.style_parts)),
        "footer": {
            "text": " ".join(" ".join(parser.footer_text).split())[:1000],
            "links": parser.footer_links[:24],
        },
    }
