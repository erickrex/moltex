"""Parsed, deterministic rewriting for immutable H2 URL and media maps."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit


def _key(url: str, origin: str) -> str:
    absolute = urljoin(origin.rstrip("/") + "/", url)
    parsed = urlsplit(absolute)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") + "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


@dataclass(slots=True)
class UrlRewriter:
    source_origin: str
    urls: dict[str, str]
    media: dict[str, str]

    def __post_init__(self) -> None:
        origin = self.source_origin
        self.urls = {_key(source, origin): target for source, target in self.urls.items()}
        self.media = {_key(source, origin): target for source, target in self.media.items()}

    def rewrite(self, value: str) -> tuple[str, bool]:
        value = value.strip()
        if not value or value.startswith(("#", "mailto:", "tel:", "data:")):
            return value, False
        parsed = urlsplit(value)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            return value, False
        key = _key(value, self.source_origin)
        target = self.media.get(key) or self.urls.get(key)
        if target is None:
            return value, False
        fragment = parsed.fragment
        if fragment:
            target = f"{target}#{fragment}"
        return target, target != value

    def rewrite_srcset(self, value: str) -> tuple[str, int]:
        output: list[str] = []
        changed = 0
        for candidate in value.split(","):
            parts = candidate.strip().split()
            if not parts:
                continue
            rewritten, did_change = self.rewrite(parts[0])
            output.append(" ".join((rewritten, *parts[1:])))
            changed += int(did_change)
        return ", ".join(output), changed
