"""Safe semantic rendering for serialized Gutenberg block comments."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


BLOCK_COMMENT = re.compile(
    r"<!--\s*(/)?wp:([a-z0-9_-]+(?:/[a-z0-9_-]+)?)"
    r"(?:\s+(\{.*?\}))?\s*(/)?-->",
    re.IGNORECASE | re.DOTALL,
)

SPECTRA_PRESENTATION_BLOCKS = frozenset(
    {
        "spectra/button",
        "spectra/buttons",
        "spectra/container",
        "spectra/content",
        "spectra/icon",
        "spectra/icons",
        "spectra/list",
        "spectra/list-child-icon",
        "spectra/list-child-item",
    }
)

ATOMIC_WIND_PRESENTATION_BLOCKS = frozenset(
    {
        "atomic-wind/box",
        "atomic-wind/icon",
        "atomic-wind/image",
        "atomic-wind/link",
        "atomic-wind/text",
    }
)

SUPPORTED_PRESENTATION_BLOCKS = (
    SPECTRA_PRESENTATION_BLOCKS | ATOMIC_WIND_PRESENTATION_BLOCKS
)

CORE_LAYOUT_BLOCKS = frozenset(
    {
        "core/audio",
        "core/buttons",
        "core/code",
        "core/column",
        "core/columns",
        "core/cover",
        "core/details",
        "core/embed",
        "core/file",
        "core/freeform",
        "core/gallery",
        "core/group",
        "core/html",
        "core/image",
        "core/list",
        "core/list-item",
        "core/media-text",
        "core/missing",
        "core/more",
        "core/nextpage",
        "core/paragraph",
        "core/post-content",
        "core/preformatted",
        "core/pullquote",
        "core/quote",
        "core/separator",
        "core/social-links",
        "core/spacer",
        "core/table",
        "core/verse",
        "core/video",
    }
)

DYNAMIC_CORE_BLOCKS = frozenset(
    {
        "core/archives",
        "core/calendar",
        "core/categories",
        "core/latest-comments",
        "core/latest-posts",
        "core/loginout",
        "core/navigation",
        "core/page-list",
        "core/post-template",
        "core/query",
        "core/query-no-results",
        "core/query-pagination",
        "core/rss",
        "core/search",
        "core/shortcode",
        "core/site-logo",
        "core/site-tagline",
        "core/site-title",
        "core/tag-cloud",
    }
)

_SAFE_TAGS = {
    "a",
    "article",
    "aside",
    "blockquote",
    "div",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "span",
    "ul",
}
_CSS_LENGTH = re.compile(r"^-?(?:\d+(?:\.\d+)?|\.\d+)(?:px|rem|em|%|vh|vw|ch)?$")
_CSS_COLOR = re.compile(
    r"^(?:#[0-9a-f]{3,8}|(?:rgb|rgba|hsl|hsla)\([0-9.%\s,/-]+\)|transparent|currentColor)$",
    re.IGNORECASE,
)
_CSS_FONT = re.compile(r"^[a-z0-9 _,-]{1,80}$", re.IGNORECASE)
_ASTRA_COLOR = re.compile(r"(?:var\(--)?ast-global-color-([0-8])(?:\))?", re.I)


@dataclass(frozen=True, slots=True)
class GutenbergRenderResult:
    html: str
    converted_blocks: int
    unresolved_blocks: int
    rewritten_urls: int


class GutenbergRenderer:
    """Translate presentation blocks while retaining safe rendered Core markup."""

    def __init__(
        self,
        rewrite_url: Callable[[str], tuple[str, bool]],
        legacy_bindings: dict[str, dict[str, str | None]],
    ) -> None:
        self.rewrite_url = rewrite_url
        self.legacy_bindings = legacy_bindings
        self.converted_blocks = 0
        self.unresolved_blocks = 0
        self.rewritten_urls = 0

    def render(self, source: str) -> GutenbergRenderResult:
        rendered = BLOCK_COMMENT.sub(self._replace, source)
        return GutenbergRenderResult(
            html=rendered,
            converted_blocks=self.converted_blocks,
            unresolved_blocks=self.unresolved_blocks,
            rewritten_urls=self.rewritten_urls,
        )

    def _replace(self, match: re.Match[str]) -> str:
        closing = bool(match.group(1))
        name = self._normalize_name(match.group(2))
        attributes = self._attributes(match.group(3))
        self_closing = bool(match.group(4))

        if name in SPECTRA_PRESENTATION_BLOCKS:
            self.converted_blocks += 1
            return self._spectra(name, attributes, closing)
        if name in ATOMIC_WIND_PRESENTATION_BLOCKS:
            self.converted_blocks += 1
            if name == "atomic-wind/icon" and self_closing and not closing:
                icon = str(attributes.get("icon") or "check")
                glyph = "✓" if icon in {"check", "check-circle"} else "•"
                return f'<span class="moltex-icon" aria-hidden="true">{glyph}</span>'
            # Atomic Wind serializes its semantic HTML between the comments. Its
            # paired comments can be discarded without losing the rendered tree.
            return ""
        if name.startswith("core/"):
            return self._core(name, attributes, closing, self_closing)
        if closing or not self_closing:
            # Paired custom blocks normally include already-rendered HTML between
            # comments. Preserve that inner markup and discard only the comments.
            return ""
        binding = self.legacy_bindings.get(f"block:{name}")
        if binding is None:
            return ""
        self.unresolved_blocks += 1
        return self._placeholder(name, binding)

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.casefold()
        return normalized if "/" in normalized else f"core/{normalized}"

    @staticmethod
    def _attributes(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _core(
        self,
        name: str,
        attributes: dict[str, Any],
        closing: bool,
        self_closing: bool,
    ) -> str:
        if name in DYNAMIC_CORE_BLOCKS and self_closing:
            self.unresolved_blocks += 1
            label = name.removeprefix("core/").replace("-", " ").title()
            return (
                '<section class="moltex-dynamic-block" '
                f'data-moltex-dynamic-block="{html.escape(name, quote=True)}" '
                f'aria-label="{html.escape(label, quote=True)}">'
                f"<h2>{html.escape(label)}</h2>"
                "<p>This WordPress-powered listing requires local data integration.</p>"
                "</section>"
            )
        if name not in CORE_LAYOUT_BLOCKS:
            return ""
        if closing:
            return "</div>"
        if self_closing:
            if name == "core/spacer":
                return f'<div class="moltex-block moltex-core-spacer"{self._style(attributes)}></div>'
            return ""
        self.converted_blocks += 1
        slug = name.removeprefix("core/")
        return (
            f'<div class="moltex-block moltex-core-block moltex-core-{slug}"'
            f'{self._style(attributes)}>'
        )

    def _spectra(
        self, name: str, attributes: dict[str, Any], closing: bool
    ) -> str:
        slug = name.removeprefix("spectra/")
        if closing:
            return {
                "container": "</div>",
                "buttons": "</div>",
                "icons": "</div>",
                "list": "</ul>",
                "list-child-item": "</li>",
            }.get(slug, "")
        if slug == "container":
            attributes = self._container_defaults(attributes)
        if slug == "content":
            tag = self._safe_tag(attributes.get("tagName"), "p")
            attributes = self._content_defaults(attributes, tag)
            text = self._safe_text(attributes.get("text", ""))
            return f'<{tag} class="moltex-block moltex-content"{self._style(attributes)}>{text}</{tag}>'
        if slug == "button":
            href = str(attributes.get("linkURL") or attributes.get("url") or "#")
            rewritten, changed = self.rewrite_url(href)
            self.rewritten_urls += int(changed)
            text = self._safe_text(attributes.get("text", "Learn more"))
            target = "_blank" if attributes.get("linkTarget") == "_blank" else "_self"
            return (
                '<a class="moltex-block moltex-button" '
                f'href="{html.escape(rewritten, quote=True)}" target="{target}"'
                f'{self._style(attributes)}>{text}<span aria-hidden="true"> →</span></a>'
            )
        if slug in {"icon", "list-child-icon"}:
            icon = str(attributes.get("icon") or "check")
            glyph = "✓" if icon in {"check", "check-circle"} else "•"
            return f'<span class="moltex-block moltex-icon" aria-hidden="true"{self._style(attributes)}>{glyph}</span>'
        tag = {
            "container": "div",
            "buttons": "div",
            "icons": "div",
            "list": "ul",
            "list-child-item": "li",
        }.get(slug, "div")
        root = " moltex-block-root" if attributes.get("isBlockRootParent") else ""
        return f'<{tag} class="moltex-block moltex-{slug}{root}"{self._style(attributes)}>'

    @staticmethod
    def _container_defaults(attributes: dict[str, Any]) -> dict[str, Any]:
        """Spectra containers with only flexWrap are vertical content stacks."""
        result = dict(attributes)

        def with_orientation(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            layout = value.get("layout")
            if not isinstance(layout, dict) or not layout:
                return value
            if (
                layout.get("type") is None
                and "flexWrap" in layout
                and "orientation" not in layout
            ):
                updated = dict(value)
                updated["layout"] = {**layout, "orientation": "vertical"}
                return updated
            return value

        result = with_orientation(result)
        responsive = result.get("responsiveControls")
        if isinstance(responsive, dict):
            result["responsiveControls"] = {
                key: with_orientation(value) for key, value in responsive.items()
            }
        return result

    @staticmethod
    def _content_defaults(attributes: dict[str, Any], tag: str) -> dict[str, Any]:
        result = dict(attributes)
        style = dict(result.get("style") or {})
        typography = dict(style.get("typography") or {})
        default_sizes = {
            "h1": "2.5rem",
            "h2": "2.25rem",
            "h3": "1.5rem",
            "h4": "1.3rem",
            "h5": "1.125rem",
            "h6": "1rem",
            "p": "1rem",
            "span": "1rem",
        }
        typography.setdefault("fontSize", default_sizes.get(tag, "1rem"))
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            typography.setdefault("fontWeight", "700")
        style["typography"] = typography
        result["style"] = style
        return result

    @staticmethod
    def _safe_text(value: Any) -> str:
        decoded = html.unescape(str(value))
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", decoded)
        return html.escape(cleaned)

    @staticmethod
    def _safe_tag(value: Any, fallback: str) -> str:
        candidate = str(value or fallback).casefold()
        return candidate if candidate in _SAFE_TAGS else fallback

    def _style(self, attributes: dict[str, Any]) -> str:
        declarations: dict[str, str] = {}
        base = dict(attributes)
        responsive = base.pop("responsiveControls", {})
        self._style_values(base, "", declarations)
        if isinstance(responsive, dict):
            for viewport in ("lg", "md", "sm"):
                values = responsive.get(viewport)
                if isinstance(values, dict):
                    self._style_values(values, f"-{viewport}", declarations)
        if not declarations:
            return ""
        value = ";".join(f"{key}:{item}" for key, item in sorted(declarations.items()))
        return f' style="{html.escape(value, quote=True)}"'

    def _style_values(
        self, attributes: dict[str, Any], suffix: str, output: dict[str, str]
    ) -> None:
        style = attributes.get("style")
        style = style if isinstance(style, dict) else {}
        spacing = style.get("spacing")
        spacing = spacing if isinstance(spacing, dict) else {}
        typography = style.get("typography")
        typography = typography if isinstance(typography, dict) else {}
        layout = attributes.get("layout")
        layout = layout if isinstance(layout, dict) else {}

        display = self._display(layout)
        self._put(output, "display", suffix, display)
        if display == "grid":
            columns = self._integer(layout.get("columnCount"), 1, 12)
            if columns:
                self._put(output, "grid-columns", suffix, f"repeat({columns},minmax(0,1fr))")
        if display == "flex":
            orientation = layout.get("orientation")
            self._put(output, "flex-direction", suffix, "column" if orientation == "vertical" else "row")
            wrap = layout.get("flexWrap")
            if wrap in {"wrap", "nowrap"}:
                self._put(output, "flex-wrap", suffix, str(wrap))
        self._put(output, "justify", suffix, self._alignment(layout.get("justifyContent"), horizontal=True))
        self._put(output, "align", suffix, self._alignment(layout.get("verticalAlignment"), horizontal=False))
        self._put(output, "gap", suffix, self._length(layout.get("gap") or spacing.get("blockGap")))

        for name, source in (
            ("width", attributes.get("width")),
            ("max-width", attributes.get("maxWidth")),
            ("min-height", attributes.get("minHeight")),
            ("height", attributes.get("height")),
        ):
            self._put(output, name, suffix, self._length(source))
        if attributes.get("align") == "full":
            self._put(output, "width", suffix, "100%")
            self._put(output, "max-width", suffix, "none")

        for box in ("padding", "margin"):
            values = spacing.get(box)
            if isinstance(values, dict):
                for side in ("top", "right", "bottom", "left"):
                    self._put(output, f"{box}-{side}", suffix, self._length(values.get(side)))

        self._put(output, "font-size", suffix, self._length(typography.get("fontSize") or attributes.get("fontSize")))
        weight = typography.get("fontWeight") or attributes.get("fontWeight")
        if str(weight) in {"100", "200", "300", "400", "500", "600", "700", "800", "900", "normal", "bold"}:
            self._put(output, "font-weight", suffix, str(weight))
        self._put(output, "line-height", suffix, self._length(typography.get("lineHeight")))
        font = typography.get("fontFamily") or attributes.get("fontFamily")
        if font and str(font) != "Default" and _CSS_FONT.fullmatch(str(font)):
            self._put(output, "font-family", suffix, str(font))

        self._put(output, "color", suffix, self._color(attributes.get("textColor") or attributes.get("color")))
        self._put(output, "background-color", suffix, self._color(attributes.get("backgroundColor")))
        border = style.get("border")
        if isinstance(border, dict):
            self._put(output, "border-width", suffix, self._length(border.get("width")))
            if border.get("style") in {"solid", "dashed", "dotted", "double", "none"}:
                self._put(output, "border-style", suffix, str(border["style"]))
            self._put(output, "border-color", suffix, self._color(border.get("color")))
            self._put(output, "border-radius", suffix, self._length(border.get("radius")))

        overlay = attributes.get("overlayImage")
        if attributes.get("overlayType") == "image" and isinstance(overlay, dict):
            url = overlay.get("url")
            if isinstance(url, str):
                rewritten, changed = self.rewrite_url(url)
                self.rewritten_urls += int(changed)
                if rewritten.startswith("/"):
                    self._put(output, "background-image", suffix, f'url("{rewritten}")')
            size = attributes.get("overlaySize")
            if size in {"cover", "contain", "auto"}:
                self._put(output, "background-size", suffix, str(size))
            x = self._length(attributes.get("overlayPositionX"))
            y = self._length(attributes.get("overlayPositionY"))
            if x and y:
                self._put(output, "background-position", suffix, f"{x} {y}")

    @staticmethod
    def _put(output: dict[str, str], name: str, suffix: str, value: str | None) -> None:
        if value is not None:
            output[f"--moltex{suffix}-{name}"] = value

    @staticmethod
    def _display(layout: dict[str, Any]) -> str | None:
        layout_type = layout.get("type")
        if layout_type == "grid":
            return "grid"
        if layout_type == "flex" or any(key in layout for key in ("orientation", "justifyContent", "verticalAlignment", "flexWrap")):
            return "flex"
        return None

    @staticmethod
    def _alignment(value: Any, *, horizontal: bool) -> str | None:
        mapping = {"left": "flex-start", "right": "flex-end", "top": "flex-start", "bottom": "flex-end", "center": "center", "stretch": "stretch", "space-between": "space-between", "space-around": "space-around"}
        result = mapping.get(str(value))
        return None if result == "stretch" and horizontal else result

    @staticmethod
    def _length(value: Any) -> str | None:
        if isinstance(value, (int, float)):
            return f"{value}px"
        candidate = str(value or "").strip()
        return candidate if _CSS_LENGTH.fullmatch(candidate) else None

    @staticmethod
    def _integer(value: Any, minimum: int, maximum: int) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if minimum <= result <= maximum else None

    @staticmethod
    def _color(value: Any) -> str | None:
        candidate = str(value or "").strip()
        match = _ASTRA_COLOR.search(candidate)
        if match:
            return f"var(--moltex-color-{match.group(1)})"
        for prefix in ("var:preset|color|ast-global-color-", "ast-global-color-"):
            if candidate.startswith(prefix):
                index = candidate.rsplit("-", 1)[-1]
                return f"var(--moltex-color-{index})" if index in "012345678" else None
        return candidate if _CSS_COLOR.fullmatch(candidate) else None

    @staticmethod
    def _placeholder(name: str, binding: dict[str, str | None]) -> str:
        attributes = [
            'class="moltex-placeholder"',
            f'data-shortcode="block:{html.escape(name, quote=True)}"',
            'role="status"',
            'aria-label="Unresolved WordPress block"',
        ]
        for key, attribute in (("evidence_id", "data-moltex-evidence"), ("capability_id", "data-moltex-capability"), ("decision_id", "data-moltex-decision")):
            if binding.get(key):
                attributes.append(f'{attribute}="{html.escape(str(binding[key]), quote=True)}"')
        return f"<div {' '.join(attributes)}>WordPress block requires replacement: {html.escape(name)}</div>"
