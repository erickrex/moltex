"""H5 report validation, normalization, metrics, and JUnit output."""

from __future__ import annotations

import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .files import stable_json
from .models import EvalCaseResult, HarnessMetrics


class VerifierReportReader:
    def read(self, workspace: Path, level: str) -> tuple[dict[str, Any], Path]:
        report_path = workspace / f".moltex/reports/verification-{level}.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Malformed or missing verifier report: {report_path}") from error
        schemas = workspace / ".moltex/schemas/verifier"
        resources: list[tuple[str, Resource[Any]]] = []
        for path in schemas.glob("*.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            resources.append((value["$id"], Resource.from_contents(value)))
        suite = json.loads(
            (schemas / "suite-report.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(
            suite, registry=Registry().with_resources(resources)
        )
        errors = sorted(validator.iter_errors(report), key=lambda item: list(item.path))
        if errors:
            raise ValueError(f"Malformed verifier report: {errors[0].message}")
        for item in report["checks"]:
            if item["status"] in {"fail", "blocked", "needs_decision", "error"} and (
                not item["subject"]
                or not item["message"]
                or (
                    item["check_id"] not in {"verification.harness", "browser.lifecycle"}
                    and (not item["contract_ids"] or not item["evidence_refs"])
                )
            ):
                raise ValueError(
                    f"Verifier finding lacks localization: {item['check_id']}"
                )
        return report, report_path


def normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(report)
    normalized.pop("started_at", None)
    normalized.pop("duration_ms", None)
    for check in normalized.get("checks", []):
        check["duration_ms"] = 0
    for process in normalized.get("processes", []):
        for key in ("pid", "port", "started_at", "duration_ms", "exit_code"):
            process.pop(key, None)
        command = process.get("command", [])
        if command:
            command[0] = "<node>"
            for index, argument in enumerate(command[:-1]):
                if argument == "--port":
                    command[index + 1] = "<port>"
    normalized["checks"] = sorted(
        normalized.get("checks", []),
        key=lambda item: (item["check_id"], item["subject"]),
    )
    return normalized


def normalized_digest(value: object) -> str:
    import hashlib

    return hashlib.sha256(stable_json(value).encode()).hexdigest()


def metrics(cases: tuple[EvalCaseResult, ...], *, repeatability: float = 1.0) -> HarnessMetrics:
    mutations = [item for item in cases if item.mutation_id]
    total = len(mutations)
    cleaned = [item for item in cases if not item.retained]
    return HarnessMetrics(
        total_cases=len(cases),
        passed_cases=sum(item.status == "pass" for item in cases),
        detected_mutations=sum(item.detected is True for item in mutations),
        localized_mutations=sum(item.localized is True for item in mutations),
        specific_mutations=sum(item.specific is True for item in mutations),
        detection_recall=(sum(item.detected is True for item in mutations) / total if total else 1.0),
        localization_rate=(sum(item.localized is True for item in mutations) / total if total else 1.0),
        specificity_rate=(sum(item.specific is True for item in mutations) / total if total else 1.0),
        cleanup_rate=(len(cleaned) / len(cases) if cases else 1.0),
        repeatability_rate=repeatability,
        total_duration_ms=sum(item.duration_ms for item in cases),
    )


def write_junit(path: Path, suite: str, cases: tuple[EvalCaseResult, ...]) -> Path:
    testsuite = ET.Element(
        "testsuite",
        name=f"moltex-{suite}",
        tests=str(len(cases)),
        failures=str(sum(item.status == "fail" for item in cases)),
        errors=str(sum(item.status == "error" for item in cases)),
        skipped=str(sum(item.status == "blocked" for item in cases)),
        time=f"{sum(item.duration_ms for item in cases) / 1000:.3f}",
    )
    for item in cases:
        case = ET.SubElement(
            testsuite,
            "testcase",
            classname=f"moltex.{item.suite}",
            name=item.case_id,
            time=f"{item.duration_ms / 1000:.3f}",
        )
        if item.status == "fail":
            ET.SubElement(case, "failure", message=item.message).text = item.message
        elif item.status == "error":
            ET.SubElement(case, "error", message=item.message).text = item.message
        elif item.status == "blocked":
            ET.SubElement(case, "skipped", message=item.message)
        ET.SubElement(case, "system-out").text = item.verifier_report or ""
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(testsuite).write(path, encoding="utf-8", xml_declaration=True)
    return path
