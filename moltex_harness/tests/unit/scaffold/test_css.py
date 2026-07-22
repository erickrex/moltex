"""Unit tests for the evidence-driven utility CSS compiler."""

from __future__ import annotations

import pytest

from moltex_harness.scaffold.css import (
    ClassToken,
    collect_class_tokens,
    compile_observed_css,
)


def _compile(tokens: list[str]):
    observed = {token: ClassToken(token=token, occurrences=1, record_ids={"r1"}) for token in tokens}
    return compile_observed_css(observed)


def _entry(result, token):
    return next(entry for entry in result.entries if entry.token == token)


def test_collect_class_tokens_counts_and_binds_records() -> None:
    observed = collect_class_tokens(
        [
            ("post:1", '<div class="flex gap-4"><span class="flex">x</span></div>'),
            ("post:2", '<section class="gap-4"></section>'),
        ]
    )
    assert observed["flex"].occurrences == 2
    assert observed["flex"].record_ids == {"post:1"}
    assert observed["gap-4"].occurrences == 2
    assert observed["gap-4"].record_ids == {"post:1", "post:2"}


@pytest.mark.parametrize(
    ("token", "declaration"),
    [
        ("inline-flex", "display:inline-flex"),
        ("rounded-2xl", "border-radius:1rem"),
        ("rounded-xl", "border-radius:0.75rem"),
        ("shadow-lg", "box-shadow:0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)"),
        ("opacity-50", "opacity:0.5"),
        ("columns-2", "columns:2"),
        ("break-inside-avoid", "break-inside:avoid"),
        ("p-4", "padding:1rem"),
        ("py-28", "padding-top:7rem"),
        ("px-8", "padding-left:2rem"),
        ("grid-cols-2", "grid-template-columns:repeat(2, minmax(0, 1fr))"),
        ("absolute", "position:absolute"),
        ("inset-0", "inset:0px"),
        ("w-1/2", "width:50%"),
        ("max-w-3xl", "max-width:48rem"),
        ("text-5xl", "font-size:3rem"),
        ("font-bold", "font-weight:700"),
    ],
)
def test_utility_families_compile(token: str, declaration: str) -> None:
    result = _compile([token])
    entry = _entry(result, token)
    assert entry.disposition == "compiled"
    assert declaration in entry.declarations


def test_responsive_variant_goes_into_media_query() -> None:
    result = _compile(["md:px-8", "lg:grid-cols-2", "md:text-5xl", "lg:text-6xl"])
    assert "@media (min-width: 768px)" in result.css
    assert "@media (min-width: 1024px)" in result.css
    assert r".md\:px-8" in result.css
    assert r".lg\:grid-cols-2" in result.css
    for token in ("md:px-8", "lg:grid-cols-2", "md:text-5xl", "lg:text-6xl"):
        assert _entry(result, token).disposition == "compiled"


def test_state_variants_build_correct_selectors() -> None:
    result = _compile(["hover:opacity-50", "group-hover:flex", "open:rounded-lg"])
    assert _entry(result, "hover:opacity-50").selector == r".hover\:opacity-50:hover"
    assert _entry(result, "group-hover:flex").selector == r".group:hover .group-hover\:flex"
    assert _entry(result, "open:rounded-lg").selector == r".open\:rounded-lg[open]"


def test_arbitrary_color_is_compiled() -> None:
    result = _compile(["bg-[#ff0000]", "text-[var(--brand)]"])
    assert "background-color:#ff0000" in _entry(result, "bg-[#ff0000]").declarations
    assert "color:var(--brand)" in _entry(result, "text-[var(--brand)]").declarations


def test_slash_opacity_uses_color_mix() -> None:
    result = _compile(["bg-[#000000]/50"])
    entry = _entry(result, "bg-[#000000]/50")
    assert entry.disposition == "compiled"
    assert "background-color:color-mix(in srgb, #000000 50%, transparent)" in entry.declarations


@pytest.mark.parametrize(
    "token",
    [
        "bg-[url(https://evil.example/x.png)]",
        "text-[expression(alert(1))]",
        "p-[10px;color:red]",
        "bg-[javascript:alert(1)]",
    ],
)
def test_unsafe_arbitrary_values_are_rejected(token: str) -> None:
    result = _compile([token])
    entry = _entry(result, token)
    assert entry.disposition == "rejected-unsafe"
    assert entry.selector is None
    assert token not in result.css


def test_unsupported_utility_is_reported_not_dropped() -> None:
    result = _compile(["some-unknown-utility"])
    entry = _entry(result, "some-unknown-utility")
    assert entry.disposition == "unsupported-safe"
    # The receipt records it even though no CSS is emitted.
    assert entry.selector is None


def test_semantic_hooks_are_classified() -> None:
    result = _compile(["wp-block-group", "moltex-button", "group", "is-layout-flex"])
    for token in ("wp-block-group", "moltex-button", "group", "is-layout-flex"):
        assert _entry(result, token).disposition == "semantic-hook"


def test_compilation_is_deterministic_regardless_of_input_order() -> None:
    tokens = ["md:px-8", "flex", "bg-[#123456]", "rounded-2xl", "lg:grid-cols-2"]
    forward = _compile(tokens)
    backward = _compile(list(reversed(tokens)))
    assert forward.css == backward.css
    assert forward.receipt() == backward.receipt()


def test_receipt_counts_and_status() -> None:
    result = _compile(["flex", "some-unknown-utility", "bg-[url(x)]"])
    receipt = result.receipt()
    assert receipt["counts"]["compiled"] == 1
    assert receipt["counts"]["unsupported-safe"] == 1
    assert receipt["counts"]["rejected-unsafe"] == 1
    assert receipt["counts"]["total"] == 3
    # Unresolved appearance-bearing tokens mean coverage is incomplete.
    assert receipt["status"] == "incomplete"


def test_receipt_status_complete_when_all_resolved() -> None:
    result = _compile(["flex", "px-8", "wp-block-group"])
    assert result.receipt()["status"] == "complete"
