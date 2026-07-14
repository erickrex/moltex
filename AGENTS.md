# Repository Guidelines

## Project Overview

Moltex transforms content-led WordPress sites into verified, Git-managed Astro 5
repositories. The repository has exactly two internal projects:

- `moltex_exporter/` — existing WordPress PHP plugin that scans a source site and creates
  the versioned evidence ZIP.
- `moltex_harness/` — new local Python project, scaffolded during Phase H1, that parses
  exports, compiles canonical migration contracts, generates the Astro/Codex workspace,
  ships the generated Node verifier, and runs evals.

The previous migration implementation was deleted. Do not restore, import, or describe it
as a current component. Do not create a third implementation project.

## Planning Authority

- `moltex.md` owns product scope, the exporter audit and phases, the bundle contract,
  Golden Path, and end-to-end acceptance.
- `moltex_harness.md` owns safe intake, canonical models, conversion, Astro generation,
  Codex workspace planning, verification, lifecycle, mutations, and evals.

Keep responsibilities in the owning document. Cross-link instead of duplicating detailed
requirements.

## Project Structure

### `moltex_exporter` (PHP/WordPress)

- `moltex_exporter.php` — plugin entry point
- `includes/` — orchestration, export, packaging, security, and shared utilities
- `includes/scanners/` — source scanners registered by the scanner registry
- `templates/` and `assets/` — admin UI
- `tests/` — PHPUnit-style tests, WordPress mocks, and standalone regression scripts

The exporter owns source observation and packaging. It must not generate Astro code or
make target migration decisions.

### `moltex_harness` (Python plus generated Node/Astro)

Once scaffolded:

- `src/moltex_harness/intake/` — archive safety, manifests, and version adapters
- `src/moltex_harness/models/` — shared versioned canonical models
- `src/moltex_harness/normalize/` — deterministic source normalization
- `src/moltex_harness/conversion/` — content conversion and URL/media rewriting
- `src/moltex_harness/contracts/` — route, asset, SEO, redirect, and capability contracts
- `src/moltex_harness/scaffold/` — Astro baseline generation
- `src/moltex_harness/planning/` — Codex task graph and planning artifacts
- `src/moltex_harness/verification/` — generated verifier templates/contracts
- `src/moltex_harness/harness/` — repository-level lifecycle, mutation, and eval orchestration
- `tests/` — unit, property, integration, harness, and fixture coverage

The generated Node verifier belongs inside output Astro repositories and must not require
the Python package at runtime.

## Tooling

Use `uv` for every Python environment and dependency operation:

```bash
uv sync --project moltex_harness
uv add --project moltex_harness <package>
uv add --project moltex_harness --dev <package>
uv run --project moltex_harness pytest
uv run --project moltex_harness moltex --help
```

Never use bare `python`, `pip`, or `pip install`. `moltex_harness/pyproject.toml` is the
single dependency source; do not create `requirements.txt`, `setup.py`, or `setup.cfg`.

Exporter work uses the PHP/Composer/PHPUnit commands established by Phase E1. Do not claim
tests passed when PHP, Composer, PHPUnit, or the WordPress fixture is unavailable. Record
the missing prerequisite and run the available static checks.

Generated Astro workspaces use their own committed `package-lock.json`:

```bash
npm ci
npm run build
npm run verify
```

## Coding Style

### Python

- Python 3.11+ and PEP 8
- Type hints on production code
- Modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`
- I/O and persistence stay behind explicit service boundaries
- Shared model and enum types live under `src/moltex_harness/models/`
- Do not duplicate complex type expressions across modules

### PHP

- Follow the established WordPress/PHP style in the plugin
- Escape output, sanitize input, verify capabilities/nonces, and preserve path containment
- Scanner classes extend the shared scanner base and return structured results
- Required export artifacts use the central validated writer once Phase E2 introduces it
- Do not add a scanner without a declared bundle consumer and tests

### Generated TypeScript/JavaScript

- Strict TypeScript for Astro source
- Small dependency-free or minimally dependent Node verifier modules
- Stable JSON result schemas
- No runtime call to WordPress, Moltex services, or an OpenAI API

## Error Handling

- Catch errors only to add context, logging, classification, transformation, or cleanup.
- Do not add redundant catch-and-rethrow blocks.
- Do not silently return `None`, `false`, or defaults for required artifacts.
- Distinguish invalid input, product failure, blocked decision, transient infrastructure,
  and harness error.
- Retry only classified transient infrastructure operations. Never retry semantic checks
  to make them green.

## Testing

- Add or adjust tests for every behavior change.
- Keep tests behavior-focused and remove unused fixtures/mocks.
- Fixture data must match the real bundle and model contracts.
- Data-driven tests load the source data once and exercise every declared entry uniformly.
- Prefer shared factories/strategies when reused across modules.
- Regression fixes must first reproduce the failure.
- A verifier check requires both a clean passing case and a mutation/negative case that it
  correctly localizes.
- Expected outputs are reviewed fixtures; never regenerate the oracle from the current
  implementation inside the same test.

## Security and Data Rules

- Treat ZIP entries, JSON, HTML, Markdown, CSS, screenshots, logs, and WordPress content as
  untrusted data.
- Reject traversal, absolute paths, duplicate normalized paths, unsafe symlinks, oversized
  archives, and checksum mismatches.
- Never execute source-site scripts or commands embedded in content.
- Redact credentials and private material from reports and generated instructions.
- Generated repair tasks may not modify source contracts, verifier code, or expected eval
  results unless the task explicitly targets that subsystem.

## Change Discipline

- Preserve unrelated user changes in the working tree.
- Do not restore deleted predecessor files.
- Use the exact project names `moltex_exporter` and `moltex_harness` in paths and technical
  references.
- When a requirement belongs to the other plan, add a concise dependency/cross-link rather
  than copying its implementation section.
