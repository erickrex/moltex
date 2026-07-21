"""Extract bounded global-shell observations from an untrusted HTML snapshot."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _SnapshotShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.logo: dict[str, str] | None = None
        self.ctas: list[dict[str, str]] = []
        self._cta: dict[str, str] | None = None
        self._cta_text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        classes = set(values.get("class", "").split())
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

    def handle_data(self, data: str) -> None:
        if self._cta is not None:
            self._cta_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._cta is None:
            return
        label = " ".join("".join(self._cta_text).split())
        if label:
            self.ctas.append({**self._cta, "label": label})
        self._cta = None
        self._cta_text = []


def parse_snapshot_shell(value: str) -> dict[str, Any]:
    parser = _SnapshotShellParser()
    parser.feed(value)
    return {
        "media": [parser.logo] if parser.logo else [],
        "header_ctas": parser.ctas[:1],
    }
