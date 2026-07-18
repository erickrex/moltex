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
uv run --project moltex_harness moltex inspect samples/golden-export.zip --json
uv run --project moltex_harness moltex compile-contracts samples/golden-export.zip --output output/golden-contracts
uv run --project moltex_harness moltex verify-contracts output/golden-contracts
uv run --project moltex_harness playwright install chromium
uv run --project moltex_harness moltex capture-source output/golden-contracts --output output/golden-source-visuals
uv run --project moltex_harness moltex compile samples/golden-export.zip --output output/golden-site --through baseline --source-visuals output/golden-source-visuals
npm --prefix output/golden-site ci
npm --prefix output/golden-site run build
uv run --project moltex_harness moltex plan-workspace output/golden-site
uv run --project moltex_harness moltex verify-task-graph output/golden-site
```

The default output directory is `output/intake/<archive-name>/`. Use
`--report-dir` to override it.

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
