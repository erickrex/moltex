"""Conservative WordPress HTML-to-editable-content conversion."""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlsplit

import nh3
from markdownify import markdownify

from moltex_harness.models import ContentConversionReceipt, ContentRecord, ConversionFinding

from .shortcodes import ShortcodeConverter
from .urls import UrlRewriter


ALLOWED_TAGS = {
    "a", "abbr", "blockquote", "br", "caption", "code", "col", "colgroup",
    "dd", "del", "details", "div", "dl", "dt", "em", "figcaption", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "img", "li", "mark", "ol",
    "p", "picture", "pre", "q", "s", "small", "source", "span", "strong",
    "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead",
    "time", "tr", "u", "ul",
}
ALLOWED_ATTRIBUTES = {
    "*": {"class", "id", "title", "role", "aria-label", "aria-hidden"},
    "a": {"href", "target"},
    "img": {"src", "srcset", "sizes", "alt", "width", "height", "loading"},
    "source": {"src", "srcset", "sizes", "type", "media"},
    "time": {"datetime"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "div": {"data-shortcode", "data-moltex-evidence", "data-moltex-capability", "data-moltex-decision"},
}
COMPLEX_TAG = re.compile(r"<(?:table|picture|details)\b", re.I)
DYNAMIC_MEDIA_PLACEHOLDERS = {"placeholder-image.jpg"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class ContentConverter:
    def __init__(
        self,
        rewriter: UrlRewriter,
        legacy_bindings: dict[str, dict[str, str | None]] | None = None,
    ) -> None:
        self.rewriter = rewriter
        self.legacy_bindings = legacy_bindings or {}

    def convert(self, record: ContentRecord) -> ContentConversionReceipt:
        original_source = record.original_html
        source = self._block_placeholders(original_source)
        shortcodes = ShortcodeConverter(
            {
                key.removeprefix("shortcode:"): value
                for key, value in self.legacy_bindings.items()
                if key.startswith("shortcode:")
            }
        ).convert(source, record.record_id)
        findings = list(shortcodes.findings)
        rewritten_count = 0
        removed_media = 0

        def filter_attribute(tag: str, name: str, value: str) -> str | None:
            nonlocal removed_media, rewritten_count
            if name in {"href", "src"}:
                value, changed = self.rewriter.rewrite(value)
                rewritten_count += int(changed)
                if (
                    name == "src"
                    and tag in {"img", "source"}
                    and (
                        urlsplit(value).scheme in {"http", "https"}
                        or urlsplit(value).path.rsplit("/", 1)[-1].casefold()
                        in DYNAMIC_MEDIA_PLACEHOLDERS
                    )
                ):
                    removed_media += 1
                    return None
            elif name == "srcset":
                value, changed_count = self.rewriter.rewrite_srcset(value)
                rewritten_count += changed_count
                candidates = []
                for candidate in value.split(","):
                    parts = candidate.strip().split()
                    if parts and urlsplit(parts[0]).scheme not in {"http", "https"}:
                        candidates.append(" ".join(parts))
                    elif parts:
                        removed_media += 1
                value = ", ".join(candidates)
                if not value:
                    return None
            return value

        sanitized = nh3.clean(
            shortcodes.html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            clean_content_tags={"script", "style", "template", "iframe", "object", "embed", "form"},
            url_schemes={"http", "https", "mailto", "tel"},
            strip_comments=True,
            link_rel="noopener noreferrer",
            attribute_filter=filter_attribute,
        ).strip()
        if removed_media:
            findings.append(
                ConversionFinding(
                    severity="warning",
                    code="unmapped_media_removed",
                    classification="blocked",
                    subject_id=record.record_id,
                    message="Unmapped or dynamic placeholder media was removed from the local-only baseline",
                    context={"attributes_removed": removed_media},
                )
            )
        source_text = self._text(shortcodes.html)
        output_text = self._text(sanitized)
        if source_text and len(output_text) < max(1, int(len(source_text) * 0.5)):
            findings.append(
                ConversionFinding(
                    severity="error",
                    code="content_loss_guard",
                    classification="permanent",
                    subject_id=record.record_id,
                    message="Sanitization removed more than half of visible source text",
                )
            )
        fallback_reason: str | None = None
        body_format: Literal["markdown", "sanitized_html"]
        if len(sanitized) > 100_000:
            body_format = "sanitized_html"
            fallback_reason = "large_content"
        elif COMPLEX_TAG.search(sanitized):
            body_format = "sanitized_html"
            fallback_reason = "complex_structure"
        else:
            body_format = "markdown"
        editable = sanitized
        if body_format == "markdown":
            try:
                editable = markdownify(sanitized, heading_style="ATX", bullets="-").strip()
                if len(self._text(editable)) < max(1, int(len(output_text) * 0.5)):
                    body_format = "sanitized_html"
                    editable = sanitized
                    fallback_reason = "markdown_content_loss"
            except (ValueError, TypeError) as error:
                body_format = "sanitized_html"
                editable = sanitized
                fallback_reason = f"markdown_error:{type(error).__name__}"
        if fallback_reason:
            findings.append(
                ConversionFinding(
                    severity="warning",
                    code="conversion_fallback",
                    classification="permanent",
                    subject_id=record.record_id,
                    message="Content uses the sanitized HTML fallback",
                    context={"reason": fallback_reason},
                )
            )
        return ContentConversionReceipt(
            record_id=record.record_id,
            source_sha256=hashlib.sha256(original_source.encode()).hexdigest(),
            output_sha256=hashlib.sha256(sanitized.encode()).hexdigest(),
            body_format=body_format,
            sanitized_html=sanitized,
            editable_body=editable,
            shortcodes=shortcodes.dispositions,
            rewritten_urls=rewritten_count,
            findings=tuple(findings),
        )

    def _block_placeholders(self, source: str) -> str:
        pattern = re.compile(
            r"<!--\s+wp:([a-z0-9_-]+/[a-z0-9_-]+)(?:\s+.*?)?\s*/-->",
            re.I | re.S,
        )

        def replace(match: re.Match[str]) -> str:
            name = match.group(1).lower()
            binding = self.legacy_bindings.get(f"block:{name}")
            if binding is None:
                return match.group(0)
            attributes = [
                'class="moltex-placeholder"',
                f'data-shortcode="block:{name}"',
                'role="status"',
                'aria-label="Unresolved WordPress block"',
            ]
            for key, attribute in (
                ("evidence_id", "data-moltex-evidence"),
                ("capability_id", "data-moltex-capability"),
                ("decision_id", "data-moltex-decision"),
            ):
                if binding.get(key):
                    attributes.append(f'{attribute}="{html.escape(str(binding[key]), quote=True)}"')
            return f"<div {' '.join(attributes)}>WordPress block requires replacement: {html.escape(name)}</div>"

        return pattern.sub(replace, source)

    @staticmethod
    def _text(value: str) -> str:
        parser = _Text()
        parser.feed(value)
        return " ".join("".join(parser.parts).split())
