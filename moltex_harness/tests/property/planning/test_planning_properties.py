from __future__ import annotations

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from moltex_harness.models import TaskEvidence


@given(
    st.sampled_from(
        ["../contract.json", "/absolute.json", "C:/secret.json", "folder\\file.json"]
    )
)
def test_task_evidence_rejects_paths_outside_workspace(path: str) -> None:
    with pytest.raises(ValidationError):
        TaskEvidence(path=path, kind="contract", reason="Unsafe path")
