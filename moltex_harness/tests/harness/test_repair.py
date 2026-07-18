from __future__ import annotations

from pathlib import Path

from moltex_harness.harness.repair import PROTECTED, RepairEvaluator


def test_repair_guard_detects_changes_to_protected_proof(tmp_path: Path) -> None:
    contracts = tmp_path / ".moltex/contracts"
    contracts.mkdir(parents=True)
    contract = contracts / "routes.json"
    contract.write_text('{"route":"/"}', encoding="utf-8")
    verifier = tmp_path / "scripts/verify.mjs"
    verifier.parent.mkdir(parents=True)
    verifier.write_text("verify();", encoding="utf-8")

    before = RepairEvaluator._protected_hashes(tmp_path)
    contract.write_text('{"route":"/weakened/"}', encoding="utf-8")
    after = RepairEvaluator._protected_hashes(tmp_path)

    assert before != after
    assert ".moltex/contracts" in PROTECTED
    assert "scripts/verify.mjs" in PROTECTED
    assert ".moltex/verification" in PROTECTED
