"""Character-scanned WordPress shortcode conversion with visible fallbacks."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from moltex_harness.models import ConversionFinding, ShortcodeDisposition


ShortcodeKind = Literal["converted", "placeholder", "preserved"]
SHORTCODE_NAME = re.compile(r"^/?[A-Za-z0-9_][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class ShortcodeResult:
    html: str
    dispositions: tuple[ShortcodeDisposition, ...]
    findings: tuple[ConversionFinding, ...]


class ShortcodeConverter:
    """Parse brackets without executing source-site shortcode handlers."""

    def __init__(self, bindings: dict[str, dict[str, str | None]] | None = None) -> None:
        self.bindings = bindings or {}

    def convert(self, source: str, subject_id: str) -> ShortcodeResult:
        counts: Counter[tuple[str, ShortcodeKind]] = Counter()
        findings: list[ConversionFinding] = []
        parser = _HtmlShortcodeParser(self, subject_id, counts, findings)
        parser.feed(source)
        parser.close()
        output = "".join(parser.output)
        dispositions = tuple(
            ShortcodeDisposition(name=name, disposition=kind, count=count)
            for (name, kind), count in sorted(counts.items())
        )
        return ShortcodeResult(output, dispositions, tuple(findings))

    def _convert_range(
        self,
        text: str,
        subject_id: str,
        counts: Counter[tuple[str, ShortcodeKind]],
        findings: list[ConversionFinding],
    ) -> str:
        out: list[str] = []
        cursor = 0
        while cursor < len(text):
            start = text.find("[", cursor)
            if start < 0:
                out.append(text[cursor:])
                break
            if start + 1 < len(text) and text[start + 1] == "[":
                escaped_end = text.find("]]", start + 2)
                if escaped_end >= 0:
                    out.append(text[cursor:start] + text[start + 1 : escaped_end + 1])
                    cursor = escaped_end + 2
                else:
                    out.append(text[cursor:start] + "[")
                    cursor = start + 2
                continue
            token = self._token(text, start)
            if token is None or token[0].startswith("/"):
                out.append(text[cursor : start + 1])
                cursor = start + 1
                continue
            raw_name, attributes, end, self_closing = token
            name = raw_name.lower()
            out.append(text[cursor:start])
            inner = ""
            next_cursor = end
            if not self_closing:
                closing = self._closing(text, end, name)
                if closing is not None:
                    inner_start, close_end = closing
                    inner = self._convert_range(
                        text[end:inner_start], subject_id, counts, findings
                    )
                    next_cursor = close_end
                elif name == "caption":
                    out.append(text[start:end])
                    cursor = end
                    continue
            replacement, kind = self._replacement(name, attributes, inner)
            counts[(name, kind)] += 1
            if kind == "placeholder":
                findings.append(
                    ConversionFinding(
                        severity="warning",
                        code="shortcode_placeholder",
                        classification="blocked",
                        subject_id=subject_id,
                        message=f"Shortcode [{name}] is represented by a baseline placeholder",
                        context={"shortcode": name},
                    )
                )
            elif kind != "converted" and name != "caption":
                findings.append(
                    ConversionFinding(
                        severity="warning",
                        code="unknown_shortcode_preserved",
                        classification="blocked",
                        subject_id=subject_id,
                        message=f"Shortcode [{name}] requires target-behavior review",
                        context={"shortcode": name},
                    )
                )
            out.append(replacement)
            cursor = next_cursor
        return "".join(out)

    @staticmethod
    def _token(text: str, start: int) -> tuple[str, str, int, bool] | None:
        quote: str | None = None
        index = start + 1
        while index < len(text):
            char = text[index]
            if quote:
                if char == quote and text[index - 1] != "\\":
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "]":
                body = text[start + 1 : index].strip()
                if not body:
                    return None
                self_closing = body.endswith("/")
                if self_closing:
                    body = body[:-1].rstrip()
                parts = body.split(None, 1)
                if not SHORTCODE_NAME.fullmatch(parts[0]):
                    return None
                return parts[0], parts[1] if len(parts) > 1 else "", index + 1, self_closing
            index += 1
        return None

    def _closing(self, text: str, cursor: int, name: str) -> tuple[int, int] | None:
        depth = 1
        while cursor < len(text):
            start = text.find("[", cursor)
            if start < 0:
                return None
            token = self._token(text, start)
            if token is None:
                cursor = start + 1
                continue
            raw, _, end, self_closing = token
            lower = raw.lower()
            if lower == name and not self_closing:
                depth += 1
            elif lower == f"/{name}":
                depth -= 1
                if depth == 0:
                    return start, end
            cursor = end
        return None

    def _replacement(
        self, name: str, attributes: str, inner: str
    ) -> tuple[str, ShortcodeKind]:
        if name == "caption":
            return f'<figure class="wp-caption">{inner}</figure>', "converted"
        if name == "gallery":
            label = html.escape(attributes or "gallery")
            return f'<div class="moltex-placeholder" data-shortcode="gallery"{self._binding_attributes(name)}>Gallery: {label}</div>', "placeholder"
        if name in {
            "contact-form-7",
            "wpforms",
            "forminator_form",
            "sureforms",
        }:
            return (
                '<form class="moltex-form" data-shortcode="form" '
                f'data-source-form="{html.escape(name, quote=True)}" '
                'aria-label="Contact form">'
                '<div class="moltex-form__grid">'
                '<label>First Name <span aria-hidden="true">*</span>'
                '<input name="first-name" autocomplete="given-name" required></label>'
                '<label>Last Name <span aria-hidden="true">*</span>'
                '<input name="last-name" autocomplete="family-name" required></label>'
                '<label class="moltex-form__wide">Email '
                '<span aria-hidden="true">*</span><input type="email" name="email" '
                'autocomplete="email" required></label>'
                '<label class="moltex-form__wide">Comment or Message '
                '<span aria-hidden="true">*</span><textarea name="message" rows="5" '
                'required></textarea></label></div>'
                '<button type="submit">Submit</button></form>',
                "converted",
            )
        if name in {
            "gd_map",
            "gd_search",
            "gd_listings",
            "gd_post_images",
            "gd_post_meta",
            "gd_loop",
            "gd_loop_paging",
        }:
            label = html.escape(name)
            return (
                f'<div class="moltex-placeholder" data-shortcode="{label}"{self._binding_attributes(name)}>'
                f"GeoDirectory component: {label}</div>",
                "placeholder",
            )
        label = html.escape(f"[{name}{(' ' + attributes) if attributes else ''}]")
        content = inner or label
        return f'<div class="moltex-placeholder" data-shortcode="{html.escape(name)}"{self._binding_attributes(name)}>{content}</div>', "preserved"

    def _binding_attributes(self, name: str) -> str:
        binding = self.bindings.get(name, {})
        values = {
            "data-moltex-evidence": binding.get("evidence_id"),
            "data-moltex-capability": binding.get("capability_id"),
            "data-moltex-decision": binding.get("decision_id"),
        }
        attributes = ' role="status" aria-label="Unresolved WordPress component"'
        for key, value in values.items():
            if value:
                attributes += f' {key}="{html.escape(str(value), quote=True)}"'
        return attributes


_SUBMIT_TYPES = {"submit", "image", "reset", "button"}
_FORM_DROP_ATTRS = {"action", "formaction", "method", "value", "src", "srcset", "form"}


def _neutralize_form_control(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    """Rebuild a start tag inside a preserved form with submission neutralized.

    Event handlers, submission targets, and pre-filled values are dropped, and
    submit/image/reset controls are downgraded to inert buttons so the static
    baseline cannot send data before an integration is approved.
    """

    safe: list[tuple[str, str]] = []
    for name, value in attrs:
        lowered = name.lower()
        if lowered.startswith("on") or lowered in _FORM_DROP_ATTRS:
            continue
        safe.append((lowered, value or ""))
    if tag in {"input", "button"}:
        rebuilt = dict(safe)
        if tag == "button" or rebuilt.get("type", "text").lower() in _SUBMIT_TYPES:
            rebuilt["type"] = "button"
        safe = list(rebuilt.items())
    rendered = "".join(
        f' {key}="{html.escape(str(value), quote=True)}"' for key, value in safe
    )
    return f"<{tag}{rendered}>"


class _HtmlShortcodeParser(HTMLParser):
    """Apply shortcode parsing only to visible text, never comments or attributes."""

    def __init__(
        self,
        converter: ShortcodeConverter,
        subject_id: str,
        counts: Counter[tuple[str, ShortcodeKind]],
        findings: list[ConversionFinding],
    ) -> None:
        super().__init__(convert_charrefs=False)
        self.converter = converter
        self.subject_id = subject_id
        self.counts = counts
        self.findings = findings
        self.output: list[str] = []
        self.form_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized == "form":
            self.form_depth += 1
            if self.form_depth == 1:
                # Preserve the form's visual structure but strip its submission
                # behavior. A separate integration decision governs whether it
                # can ever send data.
                self.output.append(
                    '<form class="moltex-form" data-moltex-form="static" '
                    'role="form" aria-label="Contact form">'
                )
                self.counts[("html-form", "preserved")] += 1
                self.findings.append(
                    ConversionFinding(
                        severity="info",
                        code="form_preserved",
                        classification="blocked",
                        subject_id=self.subject_id,
                        message=(
                            "An HTML form is preserved as a static baseline; "
                            "submission requires an approved integration"
                        ),
                    )
                )
            return
        if self.form_depth:
            self.output.append(_neutralize_form_control(normalized, attrs))
            return
        start_tag = self.get_starttag_text()
        if start_tag is not None:
            self.output.append(start_tag)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.form_depth:
            self.output.append(_neutralize_form_control(tag.lower(), attrs))
            return
        start_tag = self.get_starttag_text()
        if start_tag is not None:
            self.output.append(start_tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "form" and self.form_depth:
            self.form_depth -= 1
            if self.form_depth == 0:
                self.output.append("</form>")
            return
        if self.form_depth:
            self.output.append(f"</{normalized}>")
            return
        self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.form_depth:
            self.output.append(html.escape(data))
            return
        self.output.append(
            self.converter._convert_range(
                data, self.subject_id, self.counts, self.findings
            )
        )

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def handle_decl(self, decl: str) -> None:
        self.output.append(f"<!{decl}>")
