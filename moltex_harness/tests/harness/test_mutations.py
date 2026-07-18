from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from moltex_harness.harness.mutations import MutationCatalog


@pytest.mark.parametrize(
    "mutation_id",
    [item.mutation_id for item in MutationCatalog().list()],
)
def test_each_published_mutation_changes_one_declared_target_and_restores(
    mutation_id: str, synthetic_workspace: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / mutation_id.replace(".", "-")
    shutil.copytree(synthetic_workspace, workspace)
    catalog = MutationCatalog()

    application = catalog.apply(
        workspace, mutation_id, workspace / ".moltex/reports/mutation"
    )

    receipt = application.receipt
    assert receipt.before_sha256 != receipt.after_sha256
    assert receipt.check_id == catalog.get(mutation_id).check_id
    assert receipt.contract_ids
    assert receipt.evidence_refs
    assert (workspace / receipt.diff_artifact).is_file()

    catalog.restore(workspace, receipt.target_path, application.original)
    target = workspace / receipt.target_path
    if application.original is None:
        assert not target.exists()
    else:
        assert target.read_bytes() == application.original


def test_no_op_mutation_is_rejected_and_restored(
    synthetic_workspace: Path,
) -> None:
    page = synthetic_workspace / "dist/about/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("About Moltex", "Other"), encoding="utf-8")

    with pytest.raises(ValueError, match="changed no bytes"):
        MutationCatalog().apply(
            synthetic_workspace,
            "content.remove-marker",
            synthetic_workspace / ".moltex/reports/mutation",
        )
