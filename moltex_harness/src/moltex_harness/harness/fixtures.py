"""Immutable fixture discovery and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .files import sha256_file
from .models import FixtureSpec


FIXTURE_DATA = Path(__file__).parent / "fixture_data"


class FixtureRegistry:
    def __init__(
        self,
        fixture_root: Path | None = None,
        repository_root: Path | None = None,
    ) -> None:
        self.fixture_root = fixture_root or FIXTURE_DATA
        self.repository_root = repository_root or self._repository_root()

    def list(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                path.parent.name
                for path in self.fixture_root.glob("*/fixture.json")
            )
        )

    def load(self, fixture_id: str) -> tuple[FixtureSpec, Path]:
        if fixture_id not in self.list():
            raise ValueError(f"Unknown fixture: {fixture_id}")
        definition = self.fixture_root / fixture_id / "fixture.json"
        spec = FixtureSpec.model_validate_json(definition.read_text(encoding="utf-8"))
        source = (self.repository_root / spec.source_archive).resolve(strict=True)
        repository = self.repository_root.resolve(strict=True)
        if repository not in source.parents or not source.is_file():
            raise ValueError(f"Fixture source is outside the repository: {source}")
        actual = sha256_file(source)
        if actual != spec.source_sha256:
            raise ValueError(
                f"Fixture checksum mismatch for {fixture_id}: {actual}"
            )
        expected = (self.repository_root / spec.expected_contract_artifact).resolve(
            strict=True
        )
        if repository not in expected.parents or not expected.is_file():
            raise ValueError("Fixture expected-contract artifact is unsafe")
        if sha256_file(expected) != spec.expected_contract_revision:
            raise ValueError(
                f"Fixture expected-contract revision mismatch for {fixture_id}"
            )
        return spec, source

    @staticmethod
    def _repository_root() -> Path:
        configured = os.environ.get("MOLTEX_REPOSITORY_ROOT")
        if configured:
            return Path(configured).resolve(strict=True)
        for parent in Path(__file__).resolve().parents:
            if (parent / "samples").is_dir() and (parent / "moltex_harness").is_dir():
                return parent
        raise ValueError(
            "Cannot locate Moltex repository fixtures; set MOLTEX_REPOSITORY_ROOT"
        )

    def manifest(self, fixture_id: str) -> dict[str, object]:
        spec, source = self.load(fixture_id)
        return {
            "fixture": json.loads(spec.model_dump_json()),
            "source": str(source),
            "source_sha256": sha256_file(source),
        }
