from __future__ import annotations

from pathlib import PurePosixPath

import pytest
from hypothesis import given, strategies as st

from moltex_harness.intake.archive import ArchiveLimits, normalize_member_path
from moltex_harness.intake.errors import IntakeError
from moltex_harness.intake.serialization import deterministic_json


safe_segment = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs"),
        blacklist_characters="/\\:.",
    ),
    min_size=1,
    max_size=20,
).filter(lambda value: value not in {".", ".."} and value == value.strip())


@given(st.lists(safe_segment, min_size=1, max_size=6))
def test_safe_paths_normalize_idempotently(segments: list[str]) -> None:
    path = PurePosixPath(*segments).as_posix()
    first = normalize_member_path(path, ArchiveLimits())
    assert normalize_member_path(first, ArchiveLimits()) == first


@given(safe_segment)
def test_traversal_is_always_rejected(segment: str) -> None:
    with pytest.raises(IntakeError):
        normalize_member_path(f"{segment}/../escape", ArchiveLimits())


@given(st.dictionaries(st.text(min_size=1, max_size=8), st.integers(), max_size=12))
def test_json_serialization_is_independent_of_mapping_order(
    value: dict[str, int],
) -> None:
    reversed_value = dict(reversed(list(value.items())))
    assert deterministic_json(value) == deterministic_json(reversed_value)
