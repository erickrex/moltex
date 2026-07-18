from __future__ import annotations

from pathlib import Path

from moltex_harness.harness.processes import ProcessSupervisor
from moltex_harness.harness.toolchain import Toolchain
from moltex_harness.harness.workspace import WorkspaceFactory


def test_retained_workspace_is_reportable_and_cleanup_skips_it(tmp_path: Path) -> None:
    factory = WorkspaceFactory(
        tmp_path / "workspaces",
        ProcessSupervisor(),
        Toolchain.resolve(allow_bootstrap=False),
    )
    retained = factory.create("retained-case")
    disposable = factory.create("disposable-case")
    factory.retain(retained)

    assert factory.cleanup_all()

    assert retained.root.is_dir()
    assert not disposable.root.exists()
    assert str(retained.root).startswith(str((tmp_path / "workspaces").resolve()))
    factory.cleanup(retained)
