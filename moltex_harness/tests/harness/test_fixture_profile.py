from __future__ import annotations

from pathlib import Path

from moltex_harness.harness.fixtures import FixtureRegistry
from moltex_harness.harness.models import HarnessMode
from moltex_harness.harness.mutations import MutationCatalog
from moltex_harness.harness.profiles import ProfileFactory
from moltex_harness.harness.toolchain import Toolchain


def test_golden_fixture_is_hash_pinned() -> None:
    registry = FixtureRegistry()

    fixture, source = registry.load("golden-blog")

    assert registry.list() == ("golden-blog",)
    assert source.name == "golden-export.zip"
    assert fixture.source_sha256 == (
        "12929f58f44ce82d2f22de84bd05ce4bd24dc7a5d4160d4ff6e3fa0224253478"
    )
    assert len(fixture.mutation_ids) == 14
    assert tuple(sorted(fixture.mutation_ids)) == tuple(
        item.mutation_id for item in MutationCatalog().list()
    )


def test_profile_records_allowlisted_environment_only(
    monkeypatch, tmp_path: Path
) -> None:
    registry = FixtureRegistry()
    fixture, _ = registry.load("golden-blog")
    toolchain = Toolchain.resolve(allow_bootstrap=False)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("MOLTEX_TEST_SECRET", "must-not-appear")

    profile = ProfileFactory(registry.repository_root, toolchain).create(
        fixture,
        HarnessMode.MUTATION,
        ("mutations",),
        tmp_path,
        seed=7,
        timeout_seconds=30,
        jobs=1,
    )

    assert profile.environment.get("CI") == "true"
    assert "MOLTEX_TEST_SECRET" not in profile.environment
    assert profile.node_version == "24.14.0"
    assert profile.npm_version == "10.9.2"
