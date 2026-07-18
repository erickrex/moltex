from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Callable

import pytest
from PIL import Image, ImageDraw
from io import BytesIO

from moltex_harness.intake.service import IntakeService
from moltex_harness.normalize import ContractCompiler


REPOSITORY_ROOT = Path(__file__).parents[2]
SAMPLES = REPOSITORY_ROOT / "samples"


@pytest.fixture
def samples_dir() -> Path:
    return SAMPLES


@pytest.fixture
def rewrite_zip(tmp_path: Path) -> Callable[..., Path]:
    def rewrite(
        source: Path,
        *,
        replacements: dict[str, bytes] | None = None,
        remove: set[str] | None = None,
        output_name: str = "mutated.zip",
    ) -> Path:
        destination = tmp_path / output_name
        replacements = replacements or {}
        remove = remove or set()
        with (
            zipfile.ZipFile(source) as input_zip,
            zipfile.ZipFile(
                destination, "w", compression=zipfile.ZIP_DEFLATED
            ) as output_zip,
        ):
            for info in input_zip.infolist():
                if info.is_dir() or info.filename in remove:
                    continue
                data = replacements.get(info.filename, input_zip.read(info.filename))
                output_zip.writestr(info.filename, data)
        return destination

    return rewrite


@pytest.fixture
def minimal_legacy_zip(tmp_path: Path) -> Callable[..., Path]:
    def build(
        *,
        additions: dict[str, bytes] | None = None,
        overrides: dict[str, object] | None = None,
    ) -> Path:
        archive = tmp_path / "legacy.zip"
        documents = {
            "site_blueprint.json": {
                "schema_version": 1,
                "site": {"url": "https://example.test"},
                "content": {"total_exported": 0},
                "plugins": [],
            },
            "site_settings.json": {"schema_version": 1},
            "menus.json": {"schema_version": 1, "menus": [], "menu_locations": []},
            "export_completeness.json": {
                "schema_version": 1,
                "complete": True,
                "post_types": {},
                "excluded_statuses": ["private", "draft"],
            },
            "media/media_map.json": [],
            "migration_readiness.json": {
                "schema_version": 1,
                "eligible": True,
                "blockers": [],
            },
            "forms_config.json": {"schema_version": 1, "forms": []},
        }
        documents.update(overrides or {})
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path, value in documents.items():
                bundle.writestr(path, json.dumps(value))
            for path, value in (additions or {}).items():
                bundle.writestr(path, value)
        return archive

    return build


@pytest.fixture(scope="session")
def golden_raw_evidence(tmp_path_factory: pytest.TempPathFactory):
    report_dir = tmp_path_factory.mktemp("golden-intake")
    outcome = IntakeService().inspect(SAMPLES / "golden-export.zip", report_dir)
    assert outcome.exit_code == 0
    assert outcome.result.evidence is not None
    return outcome.result.evidence


@pytest.fixture(scope="session")
def golden_contracts(golden_raw_evidence):
    return ContractCompiler().compile(golden_raw_evidence)


@pytest.fixture
def capture_png():
    def render(width: int, height: int) -> bytes:
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, max(1, height // 5)), fill="#17324d")
        draw.rectangle(
            (width // 8, height // 3, width * 7 // 8, height * 2 // 3),
            fill="#d7e8c5",
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    return render
