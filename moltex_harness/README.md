# Moltex Harness

`moltex_harness` safely inspects versioned Moltex evidence bundles. H1 provides
bounded intake, H2 compiles evidence-linked migration contracts, H3 captures
source visual evidence and creates a conservative, buildable Astro 5 baseline,
and H4 generates and validates a bounded Codex migration task graph.

## Development

Generated Astro workspaces and their verifier use exactly Node 24.14.0 and npm
10.9.2. Install or select those versions before running the Node commands; the
generated `.node-version`, `.npmrc`, package metadata, and build script enforce
the same contract.

```powershell
uv sync --project moltex_harness
uv run --project moltex_harness pytest
uv run --project moltex_harness ruff check moltex_harness/src moltex_harness/tests
uv run --project moltex_harness mypy --config-file moltex_harness/pyproject.toml moltex_harness/src/moltex_harness
uv run --project moltex_harness playwright install chromium
uv run --project moltex_harness moltex create-site samples/golden-export.zip
```

`create-site` is the normal operator entry point. It stages all intermediate work
outside `output/` and reads the verified site name, domain, and filesystem-safe
workspace slug from the export. It publishes `output/<artifact-workspace-slug>/`
only after baseline compilation,
the locked Node build, baseline verification, H4 planning, and task-graph
verification pass. Contracts, source visuals, receipts, reports, source, and built
output all live inside that one site folder. A failed run leaves no partial site
folder, and the command never merges into an existing destination. Ineligible
contracts stop before source capture or generation. Failures retain a redacted,
bounded report under `output/.moltex-failures/<site>/<run-id>/`; success means the
workspace is built, baseline-verified, and planned, not that Codex migration work is
already complete.

The composed command prepares one immutable pipeline context: archive extraction and H1
intake run once, H2 contract compilation runs once, and H3 consumes those exact accepted
artifacts. Its final report records bounded per-stage duration, artifact-count, and byte-size
metrics without source content. Source visual targets are captured through one browser
launch with isolated pages, while route probes use a bounded worker pool, a global deadline,
and contract-order receipts.

Use `--output-root <directory>` only to place the artifact-named site beneath a
different parent directory. The CLI never accepts an operator-provided site name.

The phase-specific `inspect`, `compile-contracts`, `capture-source`, `compile`, and
`plan-workspace` commands remain available for development diagnostics. Their
required explicit output paths are not the normal multi-site output layout; `inspect`
requires `--report-dir` and never defaults to a shared `output/intake` directory.

## Intake limits

| Limit | Default |
| --- | ---: |
| Archive bytes | 100 MiB |
| Files | 5,000 |
| Total expanded bytes | 250 MiB |
| One expanded file | 50 MiB |
| JSON document | 10 MiB |
| Compression ratio | 200:1 |
| Path depth | 16 |
| Normalized path length | 240 |

Input is rejected before semantic parsing when a path is absolute, contains a
drive prefix, traversal, NUL/control characters, or backslashes; when ZIP
members are symlinks/special files; or when normalized names collide.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Accepted and inspected |
| 2 | Invalid CLI usage |
| 3 | Invalid or unsafe bundle |
| 4 | Unsupported export format |
| 5 | Harness/internal failure |
| 6 | Contract compilation or verification failure |
| 7 | Source capture or baseline generation failure |
| 8 | Task planning, graph verification, or execution-evidence failure |

## H4 Codex workspace

`moltex plan-workspace` adds `AGENTS.md`, `EXECPLAN.md`, `MIGRATION.md`, a
workspace README, Codex goal, QA plan, planning parity matrix, and one JSON and
Markdown definition per bounded task. `moltex verify-task-graph` independently
checks the DAG, timeboxes, file scope, protected paths, evidence, available and
omitted route coverage, capabilities, decisions, and planning artifacts.

After completing a task in Codex Desktop, pass its versioned
`TaskExecutionEvidence` JSON to `moltex record-task-execution`. The recorder
rejects out-of-scope changes, protected-authority changes, missing checksums, or
failed/missing verification commands before retaining the execution record.

### Capability decisions in the task graph

A capability's `required_operator_decision` value is a human-readable prompt,
not a decision identifier. H4 links a capability-disposition task to its blocking
decision by matching `DecisionItem.subject_id` to the capability's
`capability_id`, then writes the matched `DecisionItem.decision_id` into the
task's `blocking_decision_ids`. Capability-specific decisions are excluded from
the separate production decision list so that the same decision is not assigned
to two task families.

This distinction matters for exports containing plugin capabilities such as
Spectra Blocks or SureCart. Treating the prompt as an ID causes task-graph
verification to report an unknown blocking decision and stops `create-site`
during H4 planning. The compiler now fails explicitly when a capability declares
that it requires an operator decision but has no linked decision record. A unit
regression test keeps the prompt and decision ID deliberately different and
verifies that the capability task receives the real decision ID without
duplicating it on the production task.

## H3 baseline

H3 sanitizes HTML without executing WordPress code, converts known shortcodes,
retains visible placeholders for unsupported constructs, and rewrites routes and
media from the immutable H2 maps. Bundled and deferred media are materialized at
their declared `public/media/` paths before content is emitted. The generated
repository contains conversion and acquisition receipts, protected visual
evidence, a strict static Astro configuration, and a standalone Node verifier.

`npm run build` writes the Astro log, built route/asset inventories, and baseline
verification report under `.moltex/reports/`. It fails on missing route markers,
missing or changed assets, production media hotlinks, or changed visual evidence.

## H2 contract output

```text
golden-contracts/
├── source-manifest.json
├── site-spec.json
├── content-records.json
├── contracts/
│   ├── routes.json
│   ├── assets.json
│   ├── seo.json
│   ├── redirects.json
│   └── capabilities.json
├── maps/
│   ├── url-map.json
│   └── media-map.json
├── visual-capture-plan.json
├── parity-matrix.json
├── normalization-findings.json
├── decision-queue.json
└── contract-index.json
```

Canonical IDs derive from source types and IDs rather than array position. Every
migration field declares its derivation rule and source artifact/JSON-pointer
lineage. Missing references and ambiguous SEO or capability evidence are retained
as findings and `needs_decision` queue entries. URL and media maps are immutable,
and the visual plan is bounded to the homepage, one representative route per
family, and routes required for unresolved or business-critical capabilities.

Inactive plugin state is not used as a deletion rule. H1 validates the bounded
`legacy_evidence_index.json` and adapts older bundles conservatively. H2 classifies each
entry by observed public reachability: retained typed values can be converted, dormant
evidence produces no migration work, unresolved public behavior creates localized
capability/decision contracts, and deferred payloads create acquisition work. H3 emits
accessible placeholders carrying stable evidence IDs when deterministic conversion is not
possible; H4 orders any required acquisition before its consuming capability task. The
generated verifier rejects inconsistent acquisition states and missing or unlocalized
placeholders. Canonical output includes `contracts/legacy-evidence.json`.
