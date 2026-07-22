"""Evidence-driven utility CSS compiler.

This module implements workstreams CSS1 (observed class inventory) and CSS2
(bounded utility grammar) from ``css_improvements.md``. Instead of shipping a
hand-maintained whitelist of utility classes, the scaffold collects the class
tokens actually present in converted, sanitized content and compiles only the
tokens it can validate into deterministic CSS.

Design rules enforced here:

- Grammar over enumeration: bounded families of utilities are parsed and
  validated rather than enumerated one selector at a time.
- Safe values only: known keywords, a numeric spacing scale, validated lengths,
  approved CSS variables, and safe hexadecimal colors are permitted. Executable,
  URL-bearing, malformed, or unbounded arbitrary values are rejected.
- Coverage is a contract: every observed appearance-bearing token receives one
  deterministic disposition. Nothing is silently dropped; unresolved tokens are
  reported in the visual support receipt.
- Determinism: output CSS and the receipt are stable regardless of input order.

The module never inserts an unvalidated class fragment into a declaration and
never copies untrusted source CSS. It has no runtime dependency on WordPress or
any network service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

Disposition = Literal[
    "compiled",
    "semantic-hook",
    "ignored-nonvisual",
    "unsupported-safe",
    "rejected-unsafe",
]

# Bounds that keep a hostile or pathological class attribute from exhausting the
# compiler. Tokens beyond these limits are rejected as unsafe.
MAX_TOKEN_LENGTH = 120
MAX_ARBITRARY_LENGTH = 64
MAX_TOKENS_PER_RECORD = 4000

# Mobile-first breakpoints. Values are documented defaults; CSS3 may later derive
# them from source theme evidence.
BREAKPOINTS: dict[str, str] = {
    "sm": "640px",
    "md": "768px",
    "lg": "1024px",
    "xl": "1280px",
    "2xl": "1536px",
}
_RESPONSIVE_ORDER = ["", "sm", "md", "lg", "xl", "2xl"]

# State variants that have a safe, static-CSS representation.
_STATE_VARIANTS = {
    "hover",
    "focus",
    "focus-visible",
    "focus-within",
    "active",
    "open",
    "group-hover",
    "group-focus",
    "group-open",
}

# Framework / structural hooks that are intentionally not utilities. They are
# classified as semantic hooks (owned by components or block adapters) rather
# than reported as unsupported.
_SEMANTIC_PREFIXES = (
    "wp-block-",
    "wp-element-",
    "wp-container-",
    "moltex-",
    "is-",
    "has-",
    "align",
    "site-",
    "nv-",
    "elementor-",
    "screen-reader",
)
_SEMANTIC_EXACT = {
    "group",
    "wp-block",
    "aligncenter",
    "alignleft",
    "alignright",
    "clearfix",
    "sr-only",
    "not-sr-only",
}


@dataclass
class ClassToken:
    """One observed class token and where it appeared."""

    token: str
    occurrences: int = 0
    record_ids: set[str] = field(default_factory=set)


@dataclass
class SupportEntry:
    """A single row of the visual support receipt."""

    token: str
    base: str
    variants: tuple[str, ...]
    disposition: Disposition
    occurrences: int
    record_ids: tuple[str, ...]
    selector: str | None
    declarations: tuple[str, ...]
    note: str | None


@dataclass
class CssCompileResult:
    """Compiled utility CSS plus the coverage receipt."""

    css: str
    entries: list[SupportEntry]

    def receipt(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.disposition] = counts.get(entry.disposition, 0) + 1
        counts["total"] = len(self.entries)
        unresolved = counts.get("unsupported-safe", 0) + counts.get(
            "rejected-unsafe", 0
        )
        return {
            "schemaVersion": 1,
            "status": "incomplete" if unresolved else "complete",
            "counts": counts,
            "entries": [
                {
                    "token": entry.token,
                    "base": entry.base,
                    "variants": list(entry.variants),
                    "disposition": entry.disposition,
                    "occurrences": entry.occurrences,
                    "recordIds": list(entry.record_ids),
                    "selector": entry.selector,
                    "declarations": list(entry.declarations),
                    "note": entry.note,
                }
                for entry in sorted(self.entries, key=lambda item: item.token)
            ],
        }


class _ClassCollector(HTMLParser):
    """Collect class attribute tokens without executing or trusting content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if name == "class" and value:
                self.tokens.extend(value.split())

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def error(self, message: str) -> None:  # pragma: no cover - stdlib hook
        # Never raise on malformed markup; class extraction is best-effort over
        # already sanitized HTML.
        return None


def collect_class_tokens(
    sources: list[tuple[str, str]],
) -> dict[str, ClassToken]:
    """Extract observed class tokens from ``(record_id, html)`` sources."""

    observed: dict[str, ClassToken] = {}
    for record_id, html in sources:
        collector = _ClassCollector()
        try:
            collector.feed(html)
            collector.close()
        except Exception:
            # Sanitized content should not break the parser, but a defensive
            # guard keeps a single malformed record from aborting the build.
            continue
        for raw in collector.tokens[:MAX_TOKENS_PER_RECORD]:
            token = raw.strip()
            if not token:
                continue
            entry = observed.get(token)
            if entry is None:
                entry = ClassToken(token=token)
                observed[token] = entry
            entry.occurrences += 1
            entry.record_ids.add(record_id)
    return observed


def _escape_class(token: str) -> str:
    """Escape a class token for use inside a CSS selector."""

    out: list[str] = []
    for char in token:
        if char == "-" or char == "_" or (char.isascii() and char.isalnum()):
            out.append(char)
        else:
            out.append("\\" + char)
    return "".join(out)


def _split_variants(token: str) -> tuple[list[str], str]:
    """Split ``token`` into its variant chain and base, respecting brackets."""

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in token:
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        if char == ":" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts[:-1], parts[-1]


# --- value scales -----------------------------------------------------------

_SPACING_STEPS = [
    0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    14, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 72, 80, 96,
]


def _format_rem(step: float) -> str:
    if step == 0:
        return "0px"
    value = round(step * 0.25, 5)
    text = f"{value:f}".rstrip("0").rstrip(".")
    return f"{text}rem"


_SPACING: dict[str, str] = {"px": "1px"}
for _step in _SPACING_STEPS:
    _key = str(int(_step)) if float(_step).is_integer() else str(_step)
    _SPACING[_key] = _format_rem(_step)

_FRACTIONS: dict[str, str] = {}
for _num, _den in [
    (1, 2), (1, 3), (2, 3), (1, 4), (2, 4), (3, 4),
    (1, 5), (2, 5), (3, 5), (4, 5), (1, 6), (5, 6),
    (1, 12), (2, 12), (3, 12), (4, 12), (5, 12), (6, 12),
    (7, 12), (8, 12), (9, 12), (10, 12), (11, 12),
]:
    _FRACTIONS[f"{_num}/{_den}"] = f"{round(_num / _den * 100, 6):g}%"

_SIZES = {"full": "100%", "auto": "auto", "min": "min-content", "max": "max-content", "fit": "fit-content"}

_MAX_WIDTHS = {
    "none": "none", "xs": "20rem", "sm": "24rem", "md": "28rem", "lg": "32rem",
    "xl": "36rem", "2xl": "42rem", "3xl": "48rem", "4xl": "56rem", "5xl": "64rem",
    "6xl": "72rem", "7xl": "80rem", "full": "100%", "prose": "65ch",
}

_TEXT_SIZES = {
    "xs": ("0.75rem", "1rem"), "sm": ("0.875rem", "1.25rem"),
    "base": ("1rem", "1.5rem"), "lg": ("1.125rem", "1.75rem"),
    "xl": ("1.25rem", "1.75rem"), "2xl": ("1.5rem", "2rem"),
    "3xl": ("1.875rem", "2.25rem"), "4xl": ("2.25rem", "2.5rem"),
    "5xl": ("3rem", "1"), "6xl": ("3.75rem", "1"), "7xl": ("4.5rem", "1"),
    "8xl": ("6rem", "1"), "9xl": ("8rem", "1"),
}

_FONT_WEIGHTS = {
    "thin": "100", "extralight": "200", "light": "300", "normal": "400",
    "medium": "500", "semibold": "600", "bold": "700", "extrabold": "800",
    "black": "900",
}

_RADII = {
    "none": "0px", "sm": "0.125rem", "": "0.25rem", "md": "0.375rem",
    "lg": "0.5rem", "xl": "0.75rem", "2xl": "1rem", "3xl": "1.5rem",
    "full": "9999px",
}

_SHADOWS = {
    "sm": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
    "": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
    "md": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
    "lg": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
    "xl": "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
    "2xl": "0 25px 50px -12px rgb(0 0 0 / 0.25)",
    "inner": "inset 0 2px 4px 0 rgb(0 0 0 / 0.05)",
    "none": "0 0 #0000",
}

_LEADING = {
    "none": "1", "tight": "1.25", "snug": "1.375", "normal": "1.5",
    "relaxed": "1.625", "loose": "2",
}

_TRACKING = {
    "tighter": "-0.05em", "tight": "-0.025em", "normal": "0em",
    "wide": "0.025em", "wider": "0.05em", "widest": "0.1em",
}

_NAMED_COLORS = {
    "white": "#ffffff", "black": "#000000", "transparent": "transparent",
    "current": "currentColor", "inherit": "inherit",
}


# --- arbitrary-value validation --------------------------------------------

_UNSAFE = object()

_ARB_LENGTH = re.compile(r"-?\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw|vmin|vmax|ch|fr|deg)")
_ARB_HEX = re.compile(r"#[0-9a-fA-F]{3,8}")
_ARB_VAR = re.compile(r"var\(--[a-zA-Z0-9_-]{1,60}\)")
_FORBIDDEN = (
    "url(", "expression", "javascript:", "//", "\\", "<", ">", "{", "}",
    ";", "'", '"', "@", "&",
)

_Decls = list[tuple[str, str]]


def _arb(segment: str) -> str | None:
    if segment.startswith("[") and segment.endswith("]") and len(segment) > 2:
        inner = segment[1:-1]
        if len(inner) > MAX_ARBITRARY_LENGTH:
            return None
        return inner
    return None


def _unsafe_arbitrary(inner: str) -> bool:
    lowered = inner.lower()
    if any(token in lowered for token in _FORBIDDEN):
        return True
    return any(char.isspace() for char in inner)


def _resolve_color(spec: str) -> object | str | None:
    # Arbitrary values are bracketed; the optional /opacity suffix follows the
    # closing bracket. Validate the bracket content before touching the slash so
    # a hostile value such as ``[url(https://x/y)]`` cannot be split apart.
    if spec.startswith("["):
        end = spec.find("]")
        if end == -1:
            return None
        inner = spec[1:end]
        alpha_spec = spec[end + 1 :]
        if len(inner) > MAX_ARBITRARY_LENGTH:
            return None
        if _unsafe_arbitrary(inner):
            return _UNSAFE
        if _ARB_HEX.fullmatch(inner) or _ARB_VAR.fullmatch(inner):
            color = inner
        else:
            return None
    else:
        base_spec, slash, alpha = spec.partition("/")
        if base_spec not in _NAMED_COLORS:
            return None
        color = _NAMED_COLORS[base_spec]
        alpha_spec = f"/{alpha}" if slash else ""
    if alpha_spec:
        if not alpha_spec.startswith("/") or not alpha_spec[1:].isdigit():
            return None
        pct = int(alpha_spec[1:])
        if pct > 100:
            return None
        return f"color-mix(in srgb, {color} {pct}%, transparent)"
    return color


def _resolve_length(value: str, *, allow_negative: bool = False) -> object | str | None:
    negative = value.startswith("-")
    if negative:
        if not allow_negative:
            return None
        value = value[1:]
    if value in _SPACING:
        resolved = _SPACING[value]
    elif value in _FRACTIONS:
        resolved = _FRACTIONS[value]
    else:
        arb = _arb(value)
        if arb is None:
            return None
        if _unsafe_arbitrary(arb):
            return _UNSAFE
        if not _ARB_LENGTH.fullmatch(arb):
            return None
        resolved = arb
    return f"-{resolved}" if negative else resolved


_EXACT: dict[str, _Decls] = {
    "block": [("display", "block")],
    "inline-block": [("display", "inline-block")],
    "inline": [("display", "inline")],
    "flex": [("display", "flex")],
    "inline-flex": [("display", "inline-flex")],
    "grid": [("display", "grid")],
    "inline-grid": [("display", "inline-grid")],
    "hidden": [("display", "none")],
    "contents": [("display", "contents")],
    "table": [("display", "table")],
    "flow-root": [("display", "flow-root")],
    "relative": [("position", "relative")],
    "absolute": [("position", "absolute")],
    "fixed": [("position", "fixed")],
    "sticky": [("position", "sticky")],
    "static": [("position", "static")],
    "flex-row": [("flex-direction", "row")],
    "flex-row-reverse": [("flex-direction", "row-reverse")],
    "flex-col": [("flex-direction", "column")],
    "flex-col-reverse": [("flex-direction", "column-reverse")],
    "flex-wrap": [("flex-wrap", "wrap")],
    "flex-nowrap": [("flex-wrap", "nowrap")],
    "flex-wrap-reverse": [("flex-wrap", "wrap-reverse")],
    "flex-1": [("flex", "1 1 0%")],
    "flex-auto": [("flex", "1 1 auto")],
    "flex-initial": [("flex", "0 1 auto")],
    "flex-none": [("flex", "none")],
    "grow": [("flex-grow", "1")],
    "grow-0": [("flex-grow", "0")],
    "shrink": [("flex-shrink", "1")],
    "shrink-0": [("flex-shrink", "0")],
    "items-start": [("align-items", "flex-start")],
    "items-end": [("align-items", "flex-end")],
    "items-center": [("align-items", "center")],
    "items-baseline": [("align-items", "baseline")],
    "items-stretch": [("align-items", "stretch")],
    "justify-start": [("justify-content", "flex-start")],
    "justify-end": [("justify-content", "flex-end")],
    "justify-center": [("justify-content", "center")],
    "justify-between": [("justify-content", "space-between")],
    "justify-around": [("justify-content", "space-around")],
    "justify-evenly": [("justify-content", "space-evenly")],
    "content-center": [("align-content", "center")],
    "content-between": [("align-content", "space-between")],
    "content-around": [("align-content", "space-around")],
    "self-auto": [("align-self", "auto")],
    "self-start": [("align-self", "flex-start")],
    "self-end": [("align-self", "flex-end")],
    "self-center": [("align-self", "center")],
    "self-stretch": [("align-self", "stretch")],
    "text-left": [("text-align", "left")],
    "text-center": [("text-align", "center")],
    "text-right": [("text-align", "right")],
    "text-justify": [("text-align", "justify")],
    "uppercase": [("text-transform", "uppercase")],
    "lowercase": [("text-transform", "lowercase")],
    "capitalize": [("text-transform", "capitalize")],
    "normal-case": [("text-transform", "none")],
    "italic": [("font-style", "italic")],
    "not-italic": [("font-style", "normal")],
    "underline": [("text-decoration-line", "underline")],
    "line-through": [("text-decoration-line", "line-through")],
    "no-underline": [("text-decoration-line", "none")],
    "truncate": [
        ("overflow", "hidden"),
        ("text-overflow", "ellipsis"),
        ("white-space", "nowrap"),
    ],
    "break-words": [("overflow-wrap", "break-word")],
    "break-all": [("word-break", "break-all")],
    "whitespace-nowrap": [("white-space", "nowrap")],
    "whitespace-normal": [("white-space", "normal")],
    "break-inside-avoid": [("break-inside", "avoid")],
    "break-inside-avoid-column": [("break-inside", "avoid-column")],
    "overflow-hidden": [("overflow", "hidden")],
    "overflow-auto": [("overflow", "auto")],
    "overflow-visible": [("overflow", "visible")],
    "overflow-scroll": [("overflow", "scroll")],
    "overflow-x-auto": [("overflow-x", "auto")],
    "overflow-y-auto": [("overflow-y", "auto")],
    "overflow-x-hidden": [("overflow-x", "hidden")],
    "overflow-y-hidden": [("overflow-y", "hidden")],
    "object-cover": [("object-fit", "cover")],
    "object-contain": [("object-fit", "contain")],
    "object-fill": [("object-fit", "fill")],
    "object-center": [("object-position", "center")],
    "aspect-square": [("aspect-ratio", "1 / 1")],
    "aspect-video": [("aspect-ratio", "16 / 9")],
    "aspect-auto": [("aspect-ratio", "auto")],
    "isolate": [("isolation", "isolate")],
    "pointer-events-none": [("pointer-events", "none")],
    "pointer-events-auto": [("pointer-events", "auto")],
    "border-solid": [("border-style", "solid")],
    "border-dashed": [("border-style", "dashed")],
    "border-dotted": [("border-style", "dotted")],
    "border-none": [("border-style", "none")],
    "w-screen": [("width", "100vw")],
    "h-screen": [("height", "100vh")],
    "min-h-screen": [("min-height", "100vh")],
}

_SPACING_PROPS: dict[str, list[str]] = {
    "p": ["padding"],
    "px": ["padding-left", "padding-right"],
    "py": ["padding-top", "padding-bottom"],
    "pt": ["padding-top"], "pr": ["padding-right"],
    "pb": ["padding-bottom"], "pl": ["padding-left"],
    "m": ["margin"],
    "mx": ["margin-left", "margin-right"],
    "my": ["margin-top", "margin-bottom"],
    "mt": ["margin-top"], "mr": ["margin-right"],
    "mb": ["margin-bottom"], "ml": ["margin-left"],
    "gap": ["gap"], "gap-x": ["column-gap"], "gap-y": ["row-gap"],
}
_INSET_PROPS: dict[str, list[str]] = {
    "inset": ["inset"],
    "inset-x": ["left", "right"],
    "inset-y": ["top", "bottom"],
    "top": ["top"], "right": ["right"], "bottom": ["bottom"], "left": ["left"],
}
_SIZE_PROPS: dict[str, str] = {
    "w": "width", "h": "height",
    "min-w": "min-width", "min-h": "min-height",
    "max-w": "max-width", "max-h": "max-height",
    "basis": "flex-basis",
}
_Z_VALUES = {"0", "10", "20", "30", "40", "50", "auto"}
_ROUND_SIDES = {
    "": ["border-radius"],
    "t": ["border-top-left-radius", "border-top-right-radius"],
    "b": ["border-bottom-left-radius", "border-bottom-right-radius"],
    "l": ["border-top-left-radius", "border-bottom-left-radius"],
    "r": ["border-top-right-radius", "border-bottom-right-radius"],
    "tl": ["border-top-left-radius"], "tr": ["border-top-right-radius"],
    "bl": ["border-bottom-left-radius"], "br": ["border-bottom-right-radius"],
}
_BORDER_SIDES = {
    "": ["border-width"], "t": ["border-top-width"], "r": ["border-right-width"],
    "b": ["border-bottom-width"], "l": ["border-left-width"],
    "x": ["border-left-width", "border-right-width"],
    "y": ["border-top-width", "border-bottom-width"],
}
_BORDER_WIDTHS = {"0": "0px", "2": "2px", "4": "4px", "8": "8px"}
_GRADIENT_DIRS = {
    "t": "to top", "tr": "to top right", "r": "to right", "br": "to bottom right",
    "b": "to bottom", "bl": "to bottom left", "l": "to left", "tl": "to top left",
}


def _compile_base(base: str) -> object | _Decls | None:
    """Return CSS declarations for a base utility, ``None`` if unsupported.

    Returns the ``_UNSAFE`` sentinel when an arbitrary value is malformed or
    potentially hostile.
    """

    if base in _EXACT:
        return list(_EXACT[base])

    negative = base.startswith("-")
    unsigned = base[1:] if negative else base

    # Spacing: padding, margin, and gaps.
    key, _, value = unsigned.rpartition("-")
    if key in _SPACING_PROPS and value:
        allow_negative = negative and key.startswith("m")
        resolved = _resolve_length(
            f"-{value}" if allow_negative else value, allow_negative=allow_negative
        )
        if resolved is _UNSAFE:
            return _UNSAFE
        if isinstance(resolved, str):
            return [(prop, resolved) for prop in _SPACING_PROPS[key]]
        return None

    # Positioning offsets.
    if key in _INSET_PROPS and value:
        resolved = _resolve_length(
            f"-{value}" if negative else value, allow_negative=True
        )
        if resolved is _UNSAFE:
            return _UNSAFE
        if resolved == "auto" or value == "auto":
            resolved = "auto"
        if isinstance(resolved, str):
            return [(prop, resolved) for prop in _INSET_PROPS[key]]
        return None

    # Sizing.
    for prefix, prop in _SIZE_PROPS.items():
        if unsigned.startswith(prefix + "-"):
            suffix = unsigned[len(prefix) + 1 :]
            if prop == "max-width" and suffix in _MAX_WIDTHS:
                return [(prop, _MAX_WIDTHS[suffix])]
            if suffix in _SIZES:
                return [(prop, _SIZES[suffix])]
            resolved = _resolve_length(suffix)
            if resolved is _UNSAFE:
                return _UNSAFE
            if isinstance(resolved, str):
                return [(prop, resolved)]
            return None

    # Grid columns and spans.
    if unsigned.startswith("grid-cols-"):
        count = unsigned[len("grid-cols-") :]
        if count.isdigit() and 1 <= int(count) <= 12:
            return [("grid-template-columns", f"repeat({int(count)}, minmax(0, 1fr))")]
        if count == "none":
            return [("grid-template-columns", "none")]
        return None
    if unsigned.startswith("col-span-"):
        count = unsigned[len("col-span-") :]
        if count.isdigit() and 1 <= int(count) <= 12:
            return [("grid-column", f"span {int(count)} / span {int(count)}")]
        if count == "full":
            return [("grid-column", "1 / -1")]
        return None

    # Multi-column layout.
    if unsigned.startswith("columns-"):
        count = unsigned[len("columns-") :]
        if count.isdigit() and 1 <= int(count) <= 12:
            return [("columns", str(int(count)))]
        if count == "auto":
            return [("columns", "auto")]
        return None

    # Order.
    if unsigned.startswith("order-"):
        value = unsigned[len("order-") :]
        if value.isdigit() and int(value) <= 12:
            return [("order", value)]
        named_order = {"first": "-9999", "last": "9999", "none": "0"}
        if value in named_order:
            return [("order", named_order[value])]
        return None

    # z-index.
    if unsigned.startswith("z-"):
        value = unsigned[len("z-") :]
        if value in _Z_VALUES:
            return [("z-index", value)]
        return None

    # Typography.
    if base.startswith("text-"):
        suffix = base[len("text-") :]
        if suffix in _TEXT_SIZES:
            size, leading = _TEXT_SIZES[suffix]
            return [("font-size", size), ("line-height", leading)]
        arb = _arb(suffix)
        if arb is not None:
            if _unsafe_arbitrary(arb):
                return _UNSAFE
            if _ARB_LENGTH.fullmatch(arb):
                return [("font-size", arb)]
        color = _resolve_color(suffix)
        if color is _UNSAFE:
            return _UNSAFE
        if isinstance(color, str):
            return [("color", color)]
        return None
    if base.startswith("font-"):
        suffix = base[len("font-") :]
        if suffix in _FONT_WEIGHTS:
            return [("font-weight", _FONT_WEIGHTS[suffix])]
        if suffix == "sans":
            return [("font-family", "var(--moltex-body-font, ui-sans-serif, system-ui, sans-serif)")]
        if suffix == "serif":
            return [("font-family", "var(--moltex-heading-font, ui-serif, Georgia, serif)")]
        if suffix == "mono":
            return [("font-family", "ui-monospace, SFMono-Regular, Menlo, monospace")]
        return None
    if base.startswith("leading-"):
        suffix = base[len("leading-") :]
        if suffix in _LEADING:
            return [("line-height", _LEADING[suffix])]
        if suffix in _SPACING:
            return [("line-height", _SPACING[suffix])]
        return None
    if base.startswith("tracking-"):
        suffix = base[len("tracking-") :]
        if suffix in _TRACKING:
            return [("letter-spacing", _TRACKING[suffix])]
        return None

    # Border radius.
    if base == "rounded" or base.startswith("rounded-"):
        remainder = base[len("rounded") :].lstrip("-")
        side = ""
        size_key = remainder
        for candidate in ("tl", "tr", "bl", "br", "t", "b", "l", "r"):
            if remainder == candidate or remainder.startswith(candidate + "-"):
                side = candidate
                size_key = remainder[len(candidate) :].lstrip("-")
                break
        if size_key in _RADII and side in _ROUND_SIDES:
            return [(prop, _RADII[size_key]) for prop in _ROUND_SIDES[side]]
        return None

    # Shadow.
    if base == "shadow" or base.startswith("shadow-"):
        key = base[len("shadow") :].lstrip("-")
        if key in _SHADOWS:
            return [("box-shadow", _SHADOWS[key])]
        return None

    # Opacity.
    if base.startswith("opacity-"):
        value = base[len("opacity-") :]
        if value.isdigit() and int(value) <= 100:
            return [("opacity", f"{int(value) / 100:g}")]
        return None

    # Borders (width and color).
    if base == "border" or base.startswith("border-"):
        remainder = base[len("border") :].lstrip("-")
        side = ""
        rest = remainder
        for candidate in ("x", "y", "t", "r", "b", "l"):
            if remainder == candidate or remainder.startswith(candidate + "-"):
                side = candidate
                rest = remainder[len(candidate) :].lstrip("-")
                break
        if remainder == "":
            return [("border-width", "1px"), ("border-style", "solid")]
        if rest in _BORDER_WIDTHS and side in _BORDER_SIDES:
            return [(prop, _BORDER_WIDTHS[rest]) for prop in _BORDER_SIDES[side]]
        if side == "" and rest == "":
            return [("border-width", "1px"), ("border-style", "solid")]
        if side == "":
            color = _resolve_color(remainder)
            if color is _UNSAFE:
                return _UNSAFE
            if isinstance(color, str):
                return [("border-color", color)]
        return None

    # Backgrounds and gradients.
    if base.startswith("bg-gradient-to-"):
        direction = base[len("bg-gradient-to-") :]
        if direction in _GRADIENT_DIRS:
            return [
                (
                    "background-image",
                    f"linear-gradient({_GRADIENT_DIRS[direction]}, "
                    "var(--mx-gradient-from, transparent), "
                    "var(--mx-gradient-to, transparent))",
                )
            ]
        return None
    if base.startswith("from-"):
        color = _resolve_color(base[len("from-") :])
        if color is _UNSAFE:
            return _UNSAFE
        if isinstance(color, str):
            return [("--mx-gradient-from", color)]
        return None
    if base.startswith("to-"):
        color = _resolve_color(base[len("to-") :])
        if color is _UNSAFE:
            return _UNSAFE
        if isinstance(color, str):
            return [("--mx-gradient-to", color)]
        return None
    if base.startswith("bg-"):
        color = _resolve_color(base[len("bg-") :])
        if color is _UNSAFE:
            return _UNSAFE
        if isinstance(color, str):
            return [("background-color", color)]
        return None

    return None


def _is_semantic_hook(token: str, base: str) -> bool:
    if token in _SEMANTIC_EXACT or base in _SEMANTIC_EXACT:
        return True
    return any(base.startswith(prefix) for prefix in _SEMANTIC_PREFIXES)


def _build_selector(token: str, state_variants: list[str]) -> str | None:
    base_selector = "." + _escape_class(token)
    ancestors: list[str] = []
    suffix = ""
    for variant in state_variants:
        if variant == "hover":
            suffix += ":hover"
        elif variant == "focus":
            suffix += ":focus"
        elif variant == "focus-visible":
            suffix += ":focus-visible"
        elif variant == "focus-within":
            suffix += ":focus-within"
        elif variant == "active":
            suffix += ":active"
        elif variant == "open":
            suffix += "[open]"
        elif variant == "group-hover":
            ancestors.append(".group:hover")
        elif variant == "group-focus":
            ancestors.append(".group:focus")
        elif variant == "group-open":
            ancestors.append(".group[open]")
        else:
            return None
    element = base_selector + suffix
    if ancestors:
        return " ".join(ancestors + [element])
    return element


def compile_observed_css(observed: dict[str, ClassToken]) -> CssCompileResult:
    """Compile observed class tokens into deterministic utility CSS."""

    entries: list[SupportEntry] = []
    # responsive bucket -> selector -> (declarations, order-stable)
    buckets: dict[str, dict[str, _Decls]] = {key: {} for key in _RESPONSIVE_ORDER}

    for token in sorted(observed):
        record = observed[token]
        record_ids = tuple(sorted(record.record_ids))
        variants, base = _split_variants(token)

        if len(token) > MAX_TOKEN_LENGTH:
            entries.append(
                SupportEntry(token, base, tuple(variants), "rejected-unsafe",
                             record.occurrences, record_ids, None, (),
                             "token exceeds length bound")
            )
            continue

        if _is_semantic_hook(token, base):
            entries.append(
                SupportEntry(token, base, tuple(variants), "semantic-hook",
                             record.occurrences, record_ids, None, (),
                             "structural or component-owned hook")
            )
            continue

        responsive = [variant for variant in variants if variant in BREAKPOINTS]
        state = [variant for variant in variants if variant not in BREAKPOINTS]
        unknown_state = [variant for variant in state if variant not in _STATE_VARIANTS]
        if len(responsive) > 1 or unknown_state:
            entries.append(
                SupportEntry(token, base, tuple(variants), "unsupported-safe",
                             record.occurrences, record_ids, None, (),
                             "unsupported variant combination")
            )
            continue

        compiled = _compile_base(base)
        if compiled is _UNSAFE:
            entries.append(
                SupportEntry(token, base, tuple(variants), "rejected-unsafe",
                             record.occurrences, record_ids, None, (),
                             "malformed or unsafe arbitrary value")
            )
            continue
        if not compiled or not isinstance(compiled, list):
            entries.append(
                SupportEntry(token, base, tuple(variants), "unsupported-safe",
                             record.occurrences, record_ids, None, (),
                             "no grammar rule for this utility")
            )
            continue

        selector = _build_selector(token, state)
        if selector is None:
            entries.append(
                SupportEntry(token, base, tuple(variants), "unsupported-safe",
                             record.occurrences, record_ids, None, (),
                             "unsupported state variant")
            )
            continue

        bucket = responsive[0] if responsive else ""
        buckets[bucket][selector] = compiled
        entries.append(
            SupportEntry(
                token, base, tuple(variants), "compiled",
                record.occurrences, record_ids, selector,
                tuple(f"{prop}:{value}" for prop, value in compiled), None,
            )
        )

    css = _render_css(buckets)
    return CssCompileResult(css=css, entries=entries)


def _render_css(buckets: dict[str, dict[str, _Decls]]) -> str:
    lines: list[str] = [
        "",
        "/* Evidence-driven utilities compiled from observed content classes. */",
    ]
    for bucket in _RESPONSIVE_ORDER:
        rules = buckets.get(bucket, {})
        if not rules:
            continue
        indent = "  " if bucket else ""
        if bucket:
            lines.append(f"@media (min-width: {BREAKPOINTS[bucket]}) {{")
        for selector in sorted(rules):
            declarations = "; ".join(
                f"{prop}: {value}" for prop, value in rules[selector]
            )
            lines.append(f"{indent}{selector} {{ {declarations}; }}")
        if bucket:
            lines.append("}")
    return "\n".join(lines) + "\n"
