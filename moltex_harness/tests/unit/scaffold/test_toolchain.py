from __future__ import annotations

import json
from pathlib import Path

from moltex_harness.scaffold import NODE_VERSION, NPM_VERSION


TEMPLATES = (
    Path(__file__).parents[3]
    / "src/moltex_harness/scaffold/templates"
)
REPOSITORY_ROOT = Path(__file__).parents[4]


def test_generated_toolchain_declarations_are_exact_and_synchronized() -> None:
    package = json.loads((TEMPLATES / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((TEMPLATES / "package-lock.json").read_text(encoding="utf-8"))
    root_lock = lock["packages"][""]

    assert package["packageManager"] == f"npm@{NPM_VERSION}"
    assert package["engines"] == {"node": NODE_VERSION, "npm": NPM_VERSION}
    assert root_lock["engines"] == package["engines"]
    assert (TEMPLATES / ".node-version").read_text(encoding="utf-8").strip() == NODE_VERSION
    assert (REPOSITORY_ROOT / ".node-version").read_text(
        encoding="utf-8"
    ).strip() == NODE_VERSION
    assert "engine-strict=true" in (TEMPLATES / ".npmrc").read_text(
        encoding="utf-8"
    )

    build_script = (TEMPLATES / "build.mjs").read_text(encoding="utf-8")
    assert f'const expectedNode = "{NODE_VERSION}"' in build_script
    assert f'const expectedNpm = "{NPM_VERSION}"' in build_script
