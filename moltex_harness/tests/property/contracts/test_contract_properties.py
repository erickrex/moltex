from __future__ import annotations

from hypothesis import given, strategies as st

from moltex_harness.normalize import ContractCompiler
from moltex_harness.normalize.primitives import (
    normalize_gmt_datetime,
    normalize_route_path,
    stable_hash,
)


safe_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        blacklist_characters="/\\",
    ),
    min_size=1,
    max_size=16,
)


@given(st.lists(safe_segment, min_size=1, max_size=5))
def test_route_normalization_is_idempotent(segments: list[str]) -> None:
    route = "/" + "/".join(segments) + "/"
    normalized = normalize_route_path(route, "https://example.test", "always")
    assert (
        normalize_route_path(normalized, "https://example.test", "always") == normalized
    )


@given(st.datetimes(timezones=st.just(None)))
def test_gmt_date_normalization_is_idempotent(value) -> None:
    normalized = normalize_gmt_datetime(value.isoformat())
    assert normalize_gmt_datetime(normalized) == normalized


@given(st.text(min_size=1), st.text(min_size=1))
def test_stable_hash_is_deterministic(first: str, second: str) -> None:
    assert stable_hash(first, second) == stable_hash(first, second)


def test_contract_ids_do_not_depend_on_content_array_position(
    golden_raw_evidence,
) -> None:
    baseline = ContractCompiler().compile(golden_raw_evidence)
    reordered = golden_raw_evidence.model_copy(
        update={"content": list(reversed(golden_raw_evidence.content))}
    )
    changed = ContractCompiler().compile(reordered)
    assert {item.record_id for item in baseline.content_records} == {
        item.record_id for item in changed.content_records
    }
    assert {item.contract_id for item in baseline.routes} == {
        item.contract_id for item in changed.routes
    }
