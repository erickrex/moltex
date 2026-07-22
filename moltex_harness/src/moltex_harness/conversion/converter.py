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

from .gutenberg import GutenbergRenderer
from .shortcodes import ShortcodeConverter
from .urls import UrlRewriter


ALLOWED_TAGS = {
    "a", "abbr", "article", "aside", "blockquote", "br", "caption", "code", "col", "colgroup",
    "dd", "del", "details", "div", "dl", "dt", "em", "figcaption", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "img", "li", "mark", "ol",
    "button", "fieldset", "footer", "form", "header", "input", "label", "legend", "main", "nav", "option", "p", "picture", "pre", "q", "s", "section", "select", "small", "source", "span", "strong", "textarea",
    "sub", "summary", "sup", "table", "tbody", "td", "tfoot", "th", "thead",
    "time", "tr", "u", "ul",
}
ALLOWED_ATTRIBUTES = {
    "*": {
        "class", "id", "title", "role", "aria-label", "aria-hidden", "style",
        "data-moltex-block", "data-moltex-dynamic-block",
    },
    "a": {"href", "target"},
    "img": {"src", "srcset", "sizes", "alt", "width", "height", "loading"},
    "source": {"src", "srcset", "sizes", "type", "media"},
    "time": {"datetime"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "div": {"data-shortcode", "data-moltex-evidence", "data-moltex-capability", "data-moltex-decision"},
    "form": {"data-shortcode", "data-source-form", "data-moltex-form"},
    "input": {
        "type", "name", "autocomplete", "required", "placeholder", "checked",
        "min", "max", "minlength", "maxlength", "step", "pattern", "readonly",
        "disabled", "inputmode",
    },
    "textarea": {
        "name", "rows", "cols", "required", "placeholder", "maxlength",
        "minlength", "readonly", "disabled",
    },
    "select": {"name", "required", "multiple", "disabled"},
    "option": {"value", "selected", "disabled", "label"},
    "label": {"for"},
    "fieldset": {"disabled"},
    "button": {"type", "disabled"},
}
COMPLEX_TAG = re.compile(r"<(?:table|picture|details)\b", re.I)
DYNAMIC_MEDIA_PLACEHOLDERS = {"placeholder-image.jpg"}
IMAGE_TAG = re.compile(r"<img\b(?P<attributes>[^>]*)>", re.IGNORECASE)
HTML_ATTRIBUTE = re.compile(
    r'\b(?P<name>class|alt|src|srcset)="(?P<value>[^"]*)"', re.IGNORECASE
)
SAFE_INLINE_STYLE = re.compile(
    r"^(?:"
    r"--moltex(?:-(?:lg|md|sm))?-[a-z-]+|"
    r"border-radius|height|object-fit|width"
    r")$"
)
SAFE_INLINE_VALUE = re.compile(
    r"^(?:"
    r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|rem|em|%|vh|vw|ch)?|"
    r"#[0-9a-f]{3,8}|(?:rgb|rgba|hsl|hsla)\([0-9.%\s,/-]+\)|"
    r"(?:block|grid|flex|none|auto|cover|contain|fill|solid|dashed|dotted|double|nowrap|wrap|row|column|center|stretch|flex-start|flex-end|space-between|space-around|normal|bold|multiply|transparent|currentColor|repeat|repeat-x|repeat-y|no-repeat|space|round|scroll|fixed|local)|"
    r"repeat\([1-9][0-9]?,minmax\(0,1fr\)\)|"
    r"var\(--moltex-color-[0-8]\)|"
    r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|rem|em|%|vh|vw|ch)?\s+-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|rem|em|%|vh|vw|ch)?|"
    r"url\(\&quot;/[a-z0-9_./%-]+\&quot;\)|url\(\"/[a-z0-9_./%-]+\"\)"
    r")$",
    re.IGNORECASE,
)
SAFE_COMPLEX_INLINE_VALUE = re.compile(
    r"^(?:(?:linear|radial)-gradient\([#a-zA-Z0-9.%(),\s/-]{1,500}\)|"
    r"(?:inset\s+)?-?[0-9.]+(?:px|rem|em)\s+-?[0-9.]+(?:px|rem|em)"
    r"(?:\s+[0-9.]+(?:px|rem|em)){0,2}\s+"
    r"(?:#[0-9a-fA-F]{3,8}|(?:rgb|rgba|hsl|hsla)\([0-9.%\s,/-]+\)))$",
    re.IGNORECASE,
)


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
        blocks = GutenbergRenderer(
            self.rewriter.rewrite, self.legacy_bindings
        ).render(original_source)
        source = blocks.html
        shortcodes = ShortcodeConverter(
            {
                key.removeprefix("shortcode:"): value
                for key, value in self.legacy_bindings.items()
                if key.startswith("shortcode:")
            }
        ).convert(source, record.record_id)
        findings = list(shortcodes.findings)
        if blocks.converted_blocks:
            findings.append(
                ConversionFinding(
                    severity="info",
                    code="gutenberg_blocks_converted",
                    classification="permanent",
                    subject_id=record.record_id,
                    message="Serialized Gutenberg presentation blocks were converted to safe semantic HTML",
                    context={"blocks": blocks.converted_blocks},
                )
            )
        if blocks.unresolved_blocks:
            findings.append(
                ConversionFinding(
                    severity="warning",
                    code="gutenberg_blocks_unresolved",
                    classification="blocked",
                    subject_id=record.record_id,
                    message="Dynamic or unsupported Gutenberg blocks still require target behavior",
                    context={"blocks": blocks.unresolved_blocks},
                )
            )
        if blocks.unknown_icons:
            findings.append(
                ConversionFinding(
                    severity="warning",
                    code="icon_unresolved",
                    classification="blocked",
                    subject_id=record.record_id,
                    message="Unknown icon names rendered a neutral local fallback and need a registered SVG",
                    context={"icons": list(blocks.unknown_icons)},
                )
            )
        rewritten_count = blocks.rewritten_urls
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
            elif name == "style":
                declarations = []
                for declaration in value.split(";"):
                    property_name, separator, property_value = declaration.partition(":")
                    property_name = property_name.strip()
                    property_value = property_value.strip()
                    if (
                        separator
                        and SAFE_INLINE_STYLE.fullmatch(property_name)
                        and (
                            SAFE_INLINE_VALUE.fullmatch(property_value)
                            or SAFE_COMPLEX_INLINE_VALUE.fullmatch(property_value)
                        )
                    ):
                        declarations.append(f"{property_name}:{property_value}")
                return ";".join(declarations) or None
            return value

        sanitized = nh3.clean(
            shortcodes.html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            clean_content_tags={"script", "style", "template", "iframe", "object", "embed"},
            url_schemes={"http", "https", "mailto", "tel"},
            strip_comments=True,
            link_rel="noopener noreferrer",
            attribute_filter=filter_attribute,
        ).strip()
        sanitized = self._replace_src_less_images(sanitized)
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
            blocks=blocks.blocks,
            shortcodes=shortcodes.dispositions,
            rewritten_urls=rewritten_count,
            findings=tuple(findings),
        )

    @staticmethod
    def _text(value: str) -> str:
        parser = _Text()
        parser.feed(value)
        return " ".join("".join(parser.parts).split())

    @staticmethod
    def _replace_src_less_images(value: str) -> str:
        """Render unavailable media intentionally instead of a broken image icon."""

        def replace(match: re.Match[str]) -> str:
            attributes = {
                item.group("name").casefold(): html.unescape(item.group("value"))
                for item in HTML_ATTRIBUTE.finditer(match.group("attributes"))
            }
            if attributes.get("src") or attributes.get("srcset"):
                return match.group(0)
            classes = " ".join(
                part
                for part in attributes.get("class", "").split()
                if re.fullmatch(r"[a-zA-Z0-9_:\[\]()./%-]+", part)
            )
            class_value = "moltex-media-placeholder"
            if classes:
                class_value = f"{class_value} {classes}"
            label = attributes.get("alt") or "Media is not available in this export"
            return (
                f'<div class="{html.escape(class_value, quote=True)}" role="img" '
                f'aria-label="{html.escape(label, quote=True)}"></div>'
            )

        return IMAGE_TAG.sub(replace, value)
