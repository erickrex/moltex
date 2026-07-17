from pathlib import Path


def test_pinned_v1_schemas_match_exporter_contract() -> None:
    repository = Path(__file__).parents[4]
    exporter = repository / "moltex_exporter" / "schemas" / "moltex-export-1"
    pinned = (
        repository
        / "moltex_harness"
        / "src"
        / "moltex_harness"
        / "intake"
        / "schemas"
        / "moltex-export-1"
    )
    exporter_files = sorted(path.name for path in exporter.glob("*.json"))
    assert exporter_files == sorted(path.name for path in pinned.glob("*.json"))
    for filename in exporter_files:
        assert (pinned / filename).read_bytes() == (exporter / filename).read_bytes()
