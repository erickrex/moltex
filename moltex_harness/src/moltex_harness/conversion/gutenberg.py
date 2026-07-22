"""Safe semantic rendering for serialized Gutenberg block comments."""

from __future__ import annotations

import html
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

import nh3

from moltex_harness.models import BlockDisposition

from .blocks import (
    BlockConverterRegistry,
    BlockDispositionKind,
    default_block_registry,
)
from .icons import known_icon_slug


BLOCK_COMMENT = re.compile(
    r"<!--\s*(/)?wp:([a-z0-9_-]+(?:/[a-z0-9_-]+)?)"
    r"(?:\s+(\{.*?\}))?\s*(/)?-->",
    re.IGNORECASE | re.DOTALL,
)

SPECTRA_PRESENTATION_BLOCKS = frozenset(
    {
        "spectra/accordion",
        "spectra/accordion-child-details",
        "spectra/accordion-child-header",
        "spectra/accordion-child-header-content",
        "spectra/accordion-child-header-icon",
        "spectra/accordion-child-item",
        "spectra/button",
        "spectra/buttons",
        "spectra/container",
        "spectra/content",
        "spectra/google-map",
        "spectra/icon",
        "spectra/icons",
        "spectra/list",
        "spectra/list-child-icon",
        "spectra/list-child-item",
        "spectra/separator",
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
DEFAULT_BLOCK_REGISTRY = default_block_registry(
    core=CORE_LAYOUT_BLOCKS,
    dynamic=DYNAMIC_CORE_BLOCKS,
    spectra=SPECTRA_PRESENTATION_BLOCKS,
    atomic_wind=ATOMIC_WIND_PRESENTATION_BLOCKS,
)
SUPPORTED_PRESENTATION_BLOCKS = frozenset(
    spec.name
    for spec in DEFAULT_BLOCK_REGISTRY.specs
    if spec.adapter in {"spectra", "atomic-wind"}
)


@dataclass(frozen=True, slots=True)
class GutenbergRenderResult:
    html: str
    converted_blocks: int
    unresolved_blocks: int
    rewritten_urls: int
    blocks: tuple[BlockDisposition, ...]
    unknown_icons: tuple[str, ...] = ()


class GutenbergRenderer:
    """Translate presentation blocks while retaining safe rendered Core markup."""

    def __init__(
        self,
        rewrite_url: Callable[[str], tuple[str, bool]],
        legacy_bindings: dict[str, dict[str, str | None]],
        registry: BlockConverterRegistry | None = None,
    ) -> None:
        self.rewrite_url = rewrite_url
        self.legacy_bindings = legacy_bindings
        self.registry = registry or DEFAULT_BLOCK_REGISTRY
        self.converted_blocks = 0
        self.unresolved_blocks = 0
        self.rewritten_urls = 0
        self.unknown_icons: set[str] = set()
        self.block_counts: Counter[tuple[str, str, BlockDispositionKind]] = Counter()

    def render(self, source: str) -> GutenbergRenderResult:
        rendered = BLOCK_COMMENT.sub(self._replace, source)
        return GutenbergRenderResult(
            html=rendered,
            converted_blocks=self.converted_blocks,
            unresolved_blocks=self.unresolved_blocks,
            rewritten_urls=self.rewritten_urls,
            unknown_icons=tuple(sorted(self.unknown_icons)),
            blocks=tuple(
                BlockDisposition(
                    name=name,
                    namespace=name.partition("/")[0],
                    attribute_signature=signature,
                    disposition=disposition,
                    count=count,
                )
                for (name, signature, disposition), count in sorted(
                    self.block_counts.items()
                )
            ),
        )

    def _replace(self, match: re.Match[str]) -> str:
        closing = bool(match.group(1))
        name = self._normalize_name(match.group(2))
        attributes = self._attributes(match.group(3))
        self_closing = bool(match.group(4))

        if not closing:
            disposition = self.registry.resolve(
                name, self_closing=self_closing
            ).disposition
            signature = hashlib.sha256(
                json.dumps(
                    self._attribute_shape(attributes),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
            self.block_counts[(name, signature, disposition)] += 1

        spec = self.registry.resolve(name, self_closing=self_closing)
        if spec.adapter == "spectra":
            self.converted_blocks += 1
            return self._spectra(name, attributes, closing)
        if spec.adapter == "atomic-wind":
            self.converted_blocks += 1
            if name == "atomic-wind/icon" and self_closing and not closing:
                return self._icon(str(attributes.get("icon") or "check"))
            # Atomic Wind serializes its semantic HTML between the comments. Its
            # paired comments can be discarded without losing the rendered tree.
            return ""
        if spec.adapter in {"core", "dynamic"}:
            return self._core(name, attributes, closing, self_closing)
        if closing or not self_closing:
            # Paired custom blocks normally include already-rendered HTML between
            # comments. Preserve that inner markup and discard only the comments.
            return ""
        binding = self.legacy_bindings.get(f"block:{name}", {})
        self.unresolved_blocks += 1
        return self._placeholder(name, binding)

    @staticmethod
    def _attribute_shape(value: Any) -> Any:
        """Return a value-free deterministic shape for support coverage."""
        if isinstance(value, dict):
            return {
                str(key): GutenbergRenderer._attribute_shape(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, list):
            shapes = [GutenbergRenderer._attribute_shape(item) for item in value]
            return sorted(
                {
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in shapes
                }
            )
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        return "string"

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
                "accordion": "</div>",
                "accordion-child-details": "</div>",
                "accordion-child-header": "</summary>",
                "accordion-child-item": "</details>",
                "container": "</div>",
                "buttons": "</div>",
                "icons": "</div>",
                "list": "</ul>",
                "list-child-item": "</li>",
            }.get(slug, "")
        if slug == "accordion":
            return f'<div class="moltex-block moltex-accordion"{self._style(attributes)}>'
        if slug == "accordion-child-item":
            return f'<details class="moltex-block moltex-accordion__item"{self._style(attributes)}>'
        if slug == "accordion-child-header":
            return f'<summary class="moltex-block moltex-accordion__summary"{self._style(attributes)}>'
        if slug == "accordion-child-header-icon":
            return '<span class="moltex-accordion__icon" aria-hidden="true"></span>'
        if slug == "accordion-child-header-content":
            text = self._safe_text(attributes.get("text", ""))
            return f'<span class="moltex-accordion__label">{text}</span>'
        if slug == "accordion-child-details":
            return f'<div class="moltex-block moltex-accordion__details"{self._style(attributes)}>'
        if slug == "google-map":
            address = str(attributes.get("address") or "").strip()
            height = self._length(attributes.get("height")) or "350px"
            query = html.escape(address, quote=True)
            href = "https://www.google.com/maps/search/?api=1&amp;query=" + html.escape(
                address.replace(" ", "+"), quote=True
            )
            return (
                '<div class="moltex-block moltex-map" role="img" '
                f'aria-label="Map for {query}" style="--moltex-height:{height}">'
                f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f'View {html.escape(address or "location")} on Google Maps</a></div>'
            )
        if slug == "container":
            attributes = self._container_defaults(attributes)
        if slug == "content":
            tag = self._safe_tag(attributes.get("tagName"), "p")
            text = self._safe_text(attributes.get("text", ""))
            return f'<{tag} class="moltex-block moltex-content"{self._style(attributes)}>{text}</{tag}>'
        if slug == "separator":
            return (
                '<hr class="moltex-block moltex-separator"'
                f'{self._style(attributes)} aria-hidden="true">'
            )
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
            return self._icon(
                str(attributes.get("icon") or "check"),
                extra_style=self._style(attributes),
            )
        tag = {
            "container": "div",
            "buttons": "div",
            "icons": "div",
            "list": "ul",
            "list-child-item": "li",
        }.get(slug, "div")
        root = " moltex-block-root" if attributes.get("isBlockRootParent") else ""
        return f'<{tag} class="moltex-block moltex-{slug}{root}"{self._style(attributes)}>'

    # Common source aliases mapped onto registered icons.
    _ICON_ALIASES = {
        "circle-arrow-down": "arrow-down",
        "circle-arrow-right": "arrow-right",
        "star-half": "star",
        "calendar": "calendar-days",
        "user": "users",
        "book": "book-open",
    }

    def _icon(self, raw_icon: str, extra_style: str = "") -> str:
        """Render an icon as a semantic span backed by the local SVG registry."""

        alias = self._ICON_ALIASES.get(str(raw_icon).strip().casefold(), raw_icon)
        slug = known_icon_slug(alias)
        if slug is None:
            self.unknown_icons.add(str(raw_icon).strip().casefold()[:40] or "unknown")
            slug = "unknown"
        return (
            f'<span class="moltex-block moltex-icon moltex-icon--{slug}" '
            f'aria-hidden="true"{extra_style}></span>'
        )

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
    def _safe_text(value: Any) -> str:
        decoded = html.unescape(str(value))
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", decoded)
        return nh3.clean(
            cleaned,
            tags={"b", "br", "em", "i", "span", "strong", "u"},
            attributes={},
            strip_comments=True,
        )

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
                    viewport_values = dict(values)
                    viewport_values.setdefault(
                        "isBlockRootParent", base.get("isBlockRootParent")
                    )
                    self._style_values(
                        viewport_values, f"-{viewport}", declarations
                    )
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
        if layout.get("type") == "constrained":
            width_property = (
                "content-width"
                if attributes.get("isBlockRootParent")
                else "max-width"
            )
            self._put(
                output,
                width_property,
                suffix,
                self._length(layout.get("contentSize") or attributes.get("contentSize")),
            )
            self._put(
                output,
                "wide-width",
                suffix,
                self._length(layout.get("wideSize") or attributes.get("wideSize")),
            )

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
        text_align = typography.get("textAlign") or style.get("textAlign") or attributes.get("textAlign")
        if text_align in {"left", "center", "right", "justify", "start", "end"}:
            self._put(output, "text-align", suffix, str(text_align))
        font = typography.get("fontFamily") or attributes.get("fontFamily")
        if font and str(font) != "Default" and _CSS_FONT.fullmatch(str(font)):
            self._put(output, "font-family", suffix, str(font))

        self._put(output, "color", suffix, self._color(attributes.get("textColor") or attributes.get("color")))
        background_color = self._color(attributes.get("backgroundColor"))
        self._put(output, "background-color", suffix, background_color)
        self._background_styles(attributes.get("background"), suffix, output)
        if background_color and background_color.casefold().replace(" ", "").startswith(
            "rgba(0,0,0,"
        ):
            self._put(output, "background-blend-mode", suffix, "multiply")
        border = style.get("border")
        if isinstance(border, dict):
            self._put(output, "border-width", suffix, self._length(border.get("width")))
            if border.get("style") in {"solid", "dashed", "dotted", "double", "none"}:
                self._put(output, "border-style", suffix, str(border["style"]))
            self._put(output, "border-color", suffix, self._color(border.get("color")))
            radius = border.get("radius")
            if isinstance(radius, dict):
                for corner in ("topLeft", "topRight", "bottomRight", "bottomLeft"):
                    css_corner = re.sub(r"(?<!^)(?=[A-Z])", "-", corner).lower()
                    self._put(
                        output,
                        f"border-{css_corner}-radius",
                        suffix,
                        self._length(radius.get(corner)),
                    )
            else:
                self._put(output, "border-radius", suffix, self._length(radius))
            for side in ("top", "right", "bottom", "left"):
                side_value = border.get(side)
                if not isinstance(side_value, dict):
                    continue
                self._put(
                    output,
                    f"border-{side}-width",
                    suffix,
                    self._length(side_value.get("width")),
                )
                if side_value.get("style") in {
                    "solid",
                    "dashed",
                    "dotted",
                    "double",
                    "none",
                }:
                    self._put(
                        output,
                        f"border-{side}-style",
                        suffix,
                        str(side_value["style"]),
                    )
                self._put(
                    output,
                    f"border-{side}-color",
                    suffix,
                    self._color(side_value.get("color")),
                )
        shadow = style.get("shadow") or attributes.get("boxShadow")
        self._put(output, "box-shadow", suffix, self._shadow(shadow))
        gradient = (
            attributes.get("advBgGradient")
            or attributes.get("backgroundGradient")
            or style.get("gradient")
        )
        self._put(output, "background-gradient", suffix, self._gradient(gradient))
        overlay_opacity = attributes.get("overlayOpacity")
        dim_ratio = attributes.get("dimRatio")
        if (
            isinstance(overlay_opacity, (int, float))
            and 0 <= overlay_opacity <= 100
        ):
            self._put(
                output,
                "overlay-opacity",
                suffix,
                f"{overlay_opacity / 100:g}",
            )
        elif isinstance(dim_ratio, (int, float)) and 0 <= dim_ratio <= 100:
            self._put(output, "overlay-opacity", suffix, f"{dim_ratio / 100:g}")

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
            position = attributes.get("overlayPosition")
            position = position if isinstance(position, dict) else {}
            x = self._position(
                position.get("x", attributes.get("overlayPositionX"))
            )
            y = self._position(
                position.get("y", attributes.get("overlayPositionY"))
            )
            if x and y:
                self._put(output, "background-position", suffix, f"{x} {y}")

    def _background_styles(
        self, value: Any, suffix: str, output: dict[str, str]
    ) -> None:
        if not isinstance(value, dict):
            return
        media = value.get("media")
        media = media if isinstance(media, dict) else {}
        url = media.get("url")
        if isinstance(url, str):
            rewritten, changed = self.rewrite_url(url)
            self.rewritten_urls += int(changed)
            if rewritten.startswith("/"):
                self._put(output, "background-image", suffix, f'url("{rewritten}")')
        size = value.get("backgroundSize")
        if size in {"cover", "contain", "auto"}:
            self._put(output, "background-size", suffix, str(size))
        repeat = value.get("backgroundRepeat")
        if repeat in {
            "repeat",
            "repeat-x",
            "repeat-y",
            "no-repeat",
            "space",
            "round",
        }:
            self._put(output, "background-repeat", suffix, str(repeat))
        attachment = value.get("backgroundAttachment")
        if attachment in {"scroll", "fixed", "local"}:
            self._put(output, "background-attachment", suffix, str(attachment))
        position = value.get("backgroundPosition")
        if isinstance(position, dict):
            x = self._position(position.get("x"))
            y = self._position(position.get("y"))
            if x and y:
                self._put(output, "background-position", suffix, f"{x} {y}")

    @staticmethod
    def _position(value: Any) -> str | None:
        if isinstance(value, (int, float)) and 0 <= value <= 1:
            return f"{value * 100:g}%"
        return GutenbergRenderer._length(value)

    @staticmethod
    def _put(output: dict[str, str], name: str, suffix: str, value: str | None) -> None:
        if value is not None:
            output[f"--moltex{suffix}-{name}"] = value

    @staticmethod
    def _display(layout: dict[str, Any]) -> str | None:
        layout_type = layout.get("type")
        if layout_type == "grid":
            return "grid"
        if layout_type in {"constrained", "flow"}:
            return None
        if layout_type == "flex" or any(
            key in layout for key in ("orientation", "flexWrap")
        ):
            return "flex"
        return None

    @staticmethod
    def _gradient(value: Any) -> str | None:
        candidate = str(value or "").strip()
        candidate = re.sub(
            r"var\(--ast-global-color-([0-8])\)",
            lambda match: f"var(--moltex-color-{match.group(1)})",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(
            r"var:preset\|color\|ast-global-color-([0-8])",
            lambda match: f"var(--moltex-color-{match.group(1)})",
            candidate,
            flags=re.IGNORECASE,
        )
        if not re.fullmatch(
            r"(?:linear|radial)-gradient\([#a-zA-Z0-9.%(),\s/-]{1,500}\)",
            candidate,
        ):
            return None
        return candidate if "url" not in candidate.casefold() else None

    @staticmethod
    def _shadow(value: Any) -> str | None:
        candidate = str(value or "").strip()
        if re.fullmatch(
            r"(?:inset\s+)?-?[0-9.]+(?:px|rem|em)\s+-?[0-9.]+(?:px|rem|em)"
            r"(?:\s+[0-9.]+(?:px|rem|em)){0,2}\s+"
            r"(?:#[0-9a-fA-F]{3,8}|(?:rgb|rgba|hsl|hsla)\([0-9.%\s,/-]+\))",
            candidate,
        ):
            return candidate
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
