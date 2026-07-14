# Moltex Constitution

## Core Principles

### I. Plan Authority and Phase Boundaries

`moltex.md` owns exporter scope, bundle contracts, the Golden Path, and end-to-end
acceptance. `moltex_harness.md` owns harness intake through evaluation. Work MUST use only
the two existing projects, `moltex_exporter` and `moltex_harness`, and MUST NOT restore the
deleted predecessor implementation or introduce a third implementation project.

### II. Evidence Before Claims

Every phase MUST produce its declared evidence and a reproducible verification receipt.
Unavailable prerequisites, skipped checks, and known failures MUST be recorded accurately;
they MUST NOT be reported as passing. Expected fixtures are reviewed evidence and MUST NOT
be regenerated from the implementation under test.

### III. Security at Untrusted Boundaries

WordPress content, archive entries, JSON, HTML, Markdown, CSS, screenshots, and logs MUST
be treated as untrusted. Exporter changes MUST preserve capability, nonce, sanitization,
escaping, privacy filtering, and path-containment controls. Credentials and private
material MUST be excluded or redacted from fixtures, reports, and generated instructions.

### IV. Behavior-Focused Verification

Every behavior change MUST include focused test coverage. Regression fixes MUST reproduce
the failure first. Exporter work MUST run the available PHP syntax, standalone regression,
PHPUnit, and WordPress smoke checks, with missing infrastructure explicitly classified.
The exporter MUST remain the source-observation and packaging component; it MUST NOT make
target migration decisions or generate Astro code.

### V. Minimal, Reproducible Change

Changes MUST preserve unrelated work and existing behavior unless the owning phase requires
otherwise. Dependencies and commands MUST be recorded in their project-owned configuration.
Generated output and verification must be deterministic enough for independent review.

## Technology and Repository Constraints

Exporter code follows the established WordPress/PHP style. Harness Python operations use
`uv` exclusively and declare dependencies in `moltex_harness/pyproject.toml`. Generated
Astro repositories use their own committed lockfile and self-contained Node verifier.
Shared models belong under `moltex_harness/src/moltex_harness/models/`; source observation
and packaging remain under `moltex_exporter/`.

## Development Workflow and Quality Gates

Specifications MUST cite the owning plan and state explicit phase exclusions. Tasks MUST
map to testable requirements, preserve test-before-fix ordering for regressions, and end in
a separately recorded verification receipt. A phase is complete only when its exit gate is
satisfied; blocked environmental checks remain open and prevent acceptance even when all
safe local implementation work is complete.

## Governance

This constitution operationalizes `AGENTS.md`, `moltex.md`, and `moltex_harness.md` for Spec
Kit. If they conflict, repository instructions and the owning plan take precedence.
Amendments require an explicit change with rationale and a version increment. Reviews MUST
verify constitutional compliance and document justified exceptions.

**Version**: 1.0.0 | **Ratified**: 2026-07-14 | **Last Amended**: 2026-07-14
