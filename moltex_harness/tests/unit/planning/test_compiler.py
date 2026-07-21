from __future__ import annotations

from moltex_harness.contracts import ContractStore
from moltex_harness.models import DecisionItem, TaskFamily, TaskState
from moltex_harness.planning import PROTECTED_PATHS, TaskGraphCompiler
from moltex_harness.visuals.service import (
    CaptureResult,
    RouteProbeResult,
    SourceVisualService,
)


class FrozenCapture:
    def __init__(self, render) -> None:
        self.render = render

    def capture(self, target):
        return CaptureResult(
            self.render(target.viewport.width, target.viewport.height),
            target.source_url,
            "frozen-chromium",
            "1.0",
        )


class OmitRoute:
    def __init__(self, source_url: str) -> None:
        self.source_url = source_url

    def probe(self, url):
        return RouteProbeResult(404 if url == self.source_url else 200, url)


def _receipt(golden_contracts, capture_png, tmp_path, probe=None):
    contract_dir = tmp_path / "contracts"
    ContractStore().write(contract_dir, golden_contracts)
    return SourceVisualService().capture(
        contract_dir,
        tmp_path / "visuals",
        FrozenCapture(capture_png),
        probe,
    )


def test_compiler_derives_bounded_deterministic_task_graph(
    golden_contracts, capture_png, tmp_path
) -> None:
    receipt = _receipt(golden_contracts, capture_png, tmp_path)

    graph, matrix = TaskGraphCompiler().compile(golden_contracts, receipt)
    repeated, repeated_matrix = TaskGraphCompiler().compile(golden_contracts, receipt)

    assert graph == repeated
    assert matrix == repeated_matrix
    assert graph.root_task_ids == ("T001",)
    assert graph.tasks[-1].task_id == graph.final_task_id
    assert set(graph.tasks[-1].dependencies) == {
        task.task_id for task in graph.tasks[:-1]
    }
    assert all(30 <= task.estimated_minutes <= 60 for task in graph.tasks)
    assert all(
        set(PROTECTED_PATHS).issubset(task.forbidden_paths) for task in graph.tasks
    )
    route_tasks = [
        task for task in graph.tasks if task.family == TaskFamily.ROUTE_FAMILY
    ]
    assert all(len(task.contract_ids) <= 5 for task in route_tasks)
    assert {
        contract_id for task in route_tasks for contract_id in task.contract_ids
    } == {route.contract_id for route in golden_contracts.routes if route.public}
    production = next(
        task for task in graph.tasks if task.family == TaskFamily.PRODUCTION
    )
    assert "public/media/**" in production.allowed_paths


def test_confirmed_omission_has_no_task_and_is_preserved_in_parity(
    golden_contracts, capture_png, tmp_path
) -> None:
    target = golden_contracts.visual_capture_plan.targets[0]
    receipt = _receipt(
        golden_contracts,
        capture_png,
        tmp_path,
        OmitRoute(target.source_url),
    )

    graph, matrix = TaskGraphCompiler().compile(golden_contracts, receipt)

    assert all(target.route_contract_id not in task.contract_ids for task in graph.tasks)
    row = next(
        item for item in matrix.rows if item.route_contract_id == target.route_contract_id
    )
    assert row.state == "omitted"
    assert row.task_ids == ()
    assert row.omission_reason == "http_404"


def test_unresolved_non_capability_decision_blocks_production_task(
    golden_contracts, capture_png, tmp_path
) -> None:
    receipt = _receipt(golden_contracts, capture_png, tmp_path)
    evidence = golden_contracts.routes[0].lineage["contract_id"].inputs
    decision = DecisionItem(
        decision_id="decision:test:production",
        kind="production-policy",
        severity="blocking",
        subject_id="site:test",
        prompt="Choose the production policy.",
        options=("one", "two"),
        evidence=evidence,
    )
    contracts = golden_contracts.model_copy(
        update={"decisions": (*golden_contracts.decisions, decision)}
    )
    graph, _ = TaskGraphCompiler().compile(contracts, receipt)

    production = next(
        task for task in graph.tasks if task.family == TaskFamily.PRODUCTION
    )
    assert production.state == TaskState.BLOCKED
    assert production.blocking_decision_ids == (decision.decision_id,)
