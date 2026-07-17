# Moltex Harness

`moltex_harness` safely inspects versioned Moltex evidence bundles. Phase H1
provides bounded ZIP intake, manifest and checksum validation, version adapters,
and deterministic raw-source evidence. Phase H2 normalizes that evidence into
versioned, evidence-linked migration contracts without generating an Astro site.

## Development

```powershell
uv sync --project moltex_harness
uv run --project moltex_harness pytest
uv run --project moltex_harness moltex inspect samples/golden-export.zip --json
uv run --project moltex_harness moltex compile-contracts samples/golden-export.zip --output output/golden-contracts
uv run --project moltex_harness moltex verify-contracts output/golden-contracts
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
