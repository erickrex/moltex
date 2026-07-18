"""Controlled one-defect mutations with immutable receipts."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import _catalog_data
from ..files import contained, safe_relative, utc_now
from ..models import MutationDefinition, MutationReceipt


@dataclass(frozen=True, slots=True)
class MutationApplication:
    definition: MutationDefinition
    receipt: MutationReceipt
    original: bytes | None


class MutationCatalog:
    def __init__(self) -> None:
        self._definitions = {
            item.mutation_id: item for item in _catalog_data.definitions()
        }

    def list(self) -> tuple[MutationDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def get(self, mutation_id: str) -> MutationDefinition:
        try:
            return self._definitions[mutation_id]
        except KeyError as error:
            raise ValueError(f"Unknown mutation: {mutation_id}") from error

    def apply(
        self, workspace: Path, mutation_id: str, receipt_dir: Path
    ) -> MutationApplication:
        definition = self.get(mutation_id)
        receipt_dir.mkdir(parents=True, exist_ok=True)
        context = _Context(workspace)
        operation = getattr(context, mutation_id.replace(".", "_").replace("-", "_"))
        target_relative, subject, contract_ids, evidence_refs, mutate = operation()
        safe_relative(target_relative)
        target = contained(workspace, target_relative)
        original = target.read_bytes() if target.is_file() else None
        before_hash = hashlib.sha256(original).hexdigest() if original is not None else None
        mutate(target)
        changed = target.read_bytes() if target.is_file() else None
        after_hash = hashlib.sha256(changed).hexdigest() if changed is not None else None
        if before_hash == after_hash:
            self.restore(workspace, target_relative, original)
            raise ValueError(f"Mutation changed no bytes: {mutation_id}")
        diff = self._diff(target_relative, original, changed)
        diff_path = receipt_dir / "diff.patch"
        diff_path.write_text(diff, encoding="utf-8")
        receipt = MutationReceipt(
            mutation_id=mutation_id,
            check_id=definition.check_id,
            subject=subject,
            contract_ids=contract_ids,
            evidence_refs=evidence_refs,
            layer=definition.layer,
            target_path=target_relative,
            before_sha256=before_hash,
            after_sha256=after_hash,
            before_bytes=len(original) if original is not None else None,
            after_bytes=len(changed) if changed is not None else None,
            diff_artifact=diff_path.relative_to(workspace).as_posix(),
            applied_at=utc_now(),
        )
        return MutationApplication(definition, receipt, original)

    @staticmethod
    def restore(workspace: Path, relative: str, original: bytes | None) -> None:
        target = contained(workspace, relative)
        if original is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".moltex-restore")
        temporary.write_bytes(original)
        os.replace(temporary, target)

    @staticmethod
    def _diff(relative: str, before: bytes | None, after: bytes | None) -> str:
        try:
            old = (before or b"").decode("utf-8").splitlines(keepends=True)
            new = (after or b"").decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            return (
                f"Binary mutation {relative}\n"
                f"before={hashlib.sha256(before or b'').hexdigest()}\n"
                f"after={hashlib.sha256(after or b'').hexdigest()}\n"
            )
        return "".join(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )


class _Context:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.routes = self._json(".moltex/contracts/contracts/routes.json")
        self.expectations = self._json(
            ".moltex/verification/baseline-expectations.json"
        )
        self.route = next(
            item
            for item in self.routes
            if item["public"] and item["required_content_markers"]
        )

    def _json(self, relative: str) -> Any:
        return json.loads(contained(self.workspace, relative, must_exist=True).read_text(encoding="utf-8"))

    @staticmethod
    def _replace_bytes(value: bytes) -> Callable[[Path], None]:
        def replace(target: Path) -> None:
            temporary = target.with_name(target.name + ".moltex-mutation")
            temporary.write_bytes(value)
            os.replace(temporary, target)

        return replace

    @classmethod
    def _replace_json(cls, value: object) -> Callable[[Path], None]:
        return cls._replace_bytes(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        )

    def _route_output(self) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
        return (
            f"dist/{self.route['output_path']}",
            self.route["target_url"],
            (self.route["contract_id"],),
            (f".moltex/contracts/contracts/routes.json#{self.route['contract_id']}",),
        )

    def route_delete_output(self):
        relative, subject, contracts, evidence = self._route_output()
        return relative, subject, contracts, evidence, lambda target: target.unlink()

    def content_remove_marker(self):
        relative, subject, contracts, evidence = self._route_output()
        target = contained(self.workspace, relative, must_exist=True)
        marker = self.route["required_content_markers"][0]
        html = target.read_text(encoding="utf-8")
        import re

        article_match = re.search(r"<article\b[^>]*>[\s\S]*?</article>", html, re.I)
        if article_match is None or marker not in article_match.group(0):
            changed = html
        else:
            article = article_match.group(0).replace(marker, "marker removed", 1)
            changed = html[: article_match.start()] + article + html[article_match.end() :]
        return relative, subject, contracts, evidence, self._replace_bytes(changed.encode())

    def link_break_internal(self):
        relative, subject, contracts, evidence = self._route_output()
        target = contained(self.workspace, relative, must_exist=True)
        changed = target.read_text(encoding="utf-8").replace(
            "</article>", '<a href="/moltex-missing-link/">Broken</a></article>', 1
        )
        return relative, f"{subject} -> /moltex-missing-link/", contracts, evidence, self._replace_bytes(changed.encode())

    def asset_delete_local(self):
        asset = next(item for item in self._json(".moltex/contracts/contracts/assets.json") if not item["needs_decision"])
        relative = "dist/" + asset["target_path"].removeprefix("public/")
        evidence = (f".moltex/contracts/contracts/assets.json#{asset['asset_id']}",)
        return relative, asset["asset_id"], (asset["asset_id"],), evidence, lambda target: target.unlink()

    def asset_corrupt_bytes(self):
        asset = next(item for item in self._json(".moltex/contracts/contracts/assets.json") if not item["needs_decision"])
        relative = "dist/" + asset["target_path"].removeprefix("public/")
        target = contained(self.workspace, relative, must_exist=True)
        evidence = (f".moltex/contracts/contracts/assets.json#{asset['asset_id']}",)
        return relative, asset["asset_id"], (asset["asset_id"],), evidence, self._replace_bytes(target.read_bytes() + b"moltex-mutation")

    def nav_change_target(self):
        relative = "src/data/navigation.json"
        navigation = self._json(relative)
        navigation[0]["href"] = "/moltex-wrong-navigation/"
        item_id = navigation[0]["id"]
        return relative, "primary", (item_id,), (".moltex/contracts/site-spec.json", relative), self._replace_json(navigation)

    def seo_empty_title(self):
        relative, subject, _, _ = self._route_output()
        seo = next(item for item in self._json(".moltex/contracts/contracts/seo.json") if item["route_contract_id"] == self.route["contract_id"])
        target = contained(self.workspace, relative, must_exist=True)
        import re

        changed = re.sub(r"<title\b[^>]*>.*?</title>", "<title></title>", target.read_text(encoding="utf-8"), count=1)
        return relative, subject, (seo["contract_id"], self.route["contract_id"]), (f".moltex/contracts/contracts/seo.json#{seo['contract_id']}",), self._replace_bytes(changed.encode())

    def seo_wrong_canonical(self):
        relative, subject, _, _ = self._route_output()
        seo = next(item for item in self._json(".moltex/contracts/contracts/seo.json") if item["route_contract_id"] == self.route["contract_id"])
        target = contained(self.workspace, relative, must_exist=True)
        import re

        changed = re.sub(r'(<link\b(?=[^>]*rel=["\']canonical["\'])[^>]*href=["\'])[^"\']*', r"\1https://wrong.invalid/", target.read_text(encoding="utf-8"), count=1)
        return relative, subject, (seo["contract_id"], self.route["contract_id"]), (f".moltex/contracts/contracts/seo.json#{seo['contract_id']}",), self._replace_bytes(changed.encode())

    def redirect_create_loop(self):
        relative = ".moltex/contracts/contracts/redirects.json"
        redirects = [
            {"contract_id": "redirect:mutation:a", "source_url": "/__moltex_a/", "target_url": "/__moltex_b/", "needs_decision": False},
            {"contract_id": "redirect:mutation:b", "source_url": "/__moltex_b/", "target_url": "/__moltex_a/", "needs_decision": False},
        ]
        return relative, "/__moltex_a/", ("redirect:mutation:a",), (".moltex/contracts/contracts/redirects.json#redirect:mutation:a",), self._replace_json(redirects)

    def capability_remove_disposition(self):
        relative = ".moltex/contracts/contracts/capabilities.json"
        capabilities = self._json(relative)
        capability = next((item for item in capabilities if item["business_critical"]), capabilities[0])
        changed = [item for item in capabilities if item["capability_id"] != capability["capability_id"]]
        identifier = capability["capability_id"]
        return relative, identifier, (identifier,), (".moltex/contracts/site-spec.json", f"{relative}#{identifier}"), self._replace_json(changed)

    def parity_duplicate_row(self):
        relative = ".moltex/parity-matrix.json"
        matrix = self._json(relative)
        matrix["rows"].append(matrix["rows"][0])
        row = matrix["rows"][0]
        return relative, "parity-matrix", (row["row_id"],), (relative,), self._replace_json(matrix)

    def task_false_complete(self):
        relative = ".moltex/tasks/task-graph.json"
        graph = self._json(relative)
        task = next(item for item in graph["tasks"] if item["contract_ids"])
        task["state"] = "complete"
        contracts = tuple(task["contract_ids"])
        return relative, task["task_id"], contracts, (f".moltex/tasks/{task['task_id']}.json",), self._replace_json(graph)

    def browser_console_error(self):
        relative, subject, contracts, evidence = self._route_output()
        target = contained(self.workspace, relative, must_exist=True)
        changed = target.read_text(encoding="utf-8").replace(
            "</body>", '<script>console.error("moltex mutation")</script></body>', 1
        )
        return relative, subject, contracts, evidence, self._replace_bytes(changed.encode())

    def a11y_remove_name(self):
        relative, subject, contracts, evidence = self._route_output()
        target = contained(self.workspace, relative, must_exist=True)
        changed = target.read_text(encoding="utf-8").replace(
            ' aria-label="Primary"', "", 1
        )
        return relative, subject, contracts, evidence, self._replace_bytes(changed.encode())
