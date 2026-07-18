from __future__ import annotations

from hypothesis import given, strategies as st

from moltex_harness.conversion import UrlRewriter


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=100))
def test_unmapped_values_are_stable(value: str) -> None:
    rewriter = UrlRewriter("https://source.test", {}, {})
    first, _ = rewriter.rewrite(value)
    second, changed = rewriter.rewrite(first)
    assert second == first
    assert not changed


@given(st.sampled_from(["/about/", "/about/#team", "https://source.test/about/"]))
def test_route_rewrite_is_idempotent(value: str) -> None:
    rewriter = UrlRewriter(
        "https://source.test", {"https://source.test/about/": "/about/"}, {}
    )
    first, _ = rewriter.rewrite(value)
    second, changed = rewriter.rewrite(first)
    assert second == first
    assert not changed
