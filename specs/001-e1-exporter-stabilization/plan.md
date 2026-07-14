# Implementation Plan: E1 Exporter Stabilization

**Branch**: `master` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Phase E1 from `moltex.md`, constrained to the existing `moltex_exporter`.

## Summary

Audit the current scanner/artifact surface, make the exporter test environment executable,
repair verified regressions without changing the legacy contract, remove stale identity,
exercise complete and discovery exports in disposable WordPress, and freeze sanitized
`legacy-1` evidence with a separate verification receipt.

## Technical Context

**Language/Version**: Production PHP 7.4+; E1 verification baseline PHP 8.2.31

**Primary Dependencies**: WordPress 7.0.1 smoke fixture, Composer 2, PHPUnit 9.6,
PHP extensions required by WordPress plus ZipArchive, and Docker Desktop for the disposable
WordPress/MariaDB environment

**Storage**: WordPress database and filesystem in disposable test containers; reviewed
Markdown/JSON/ZIP evidence in the repository

**Testing**: `php -l`, four standalone regression scripts, PHPUnit, static identity/privacy
searches, checksum verification, and complete/discovery WordPress smoke exports

**Target Platform**: WordPress plugin on PHP 7.4+; reproducible E1 checks on Windows with
PowerShell plus Linux containers for the disposable WordPress site

**Project Type**: Existing WordPress plugin and its tests/documentation

**Performance Goals**: No new performance claim; record size risks and exercise both export
modes on the bounded smoke fixture

**Constraints**: Preserve current `legacy-1` behavior; no E2 schema/manifest work, no Astro
generation, no harness runtime dependency, no private data in committed evidence

**Scale/Scope**: 33 registered scanners, all discovered emitted artifact patterns, six
declared local verification commands, and one complete/discovery smoke pair

## Constitution Check

*GATE: Passed before research and re-checked after design.*

- Plan authority: PASS — scope comes directly from E1 in `moltex.md`.
- Project boundary: PASS — changes remain in `moltex_exporter`, shared docs, and E1 specs.
- Evidence before claims: PASS — every command receives a recorded status and receipt.
- Untrusted-data security: PASS — fixture generation includes sanitization and manual review.
- Behavior-focused verification: PASS — regressions precede fixes and WordPress smoke is explicit.
- Minimal reproducible change: PASS — E2 contract changes and harness implementation are excluded.

## Project Structure

### Documentation (this feature)

```text
specs/001-e1-exporter-stabilization/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── evidence.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code and Evidence (repository root)

```text
moltex_exporter/
├── moltex_exporter.php
├── composer.json
├── composer.lock
├── phpunit.xml.dist
├── includes/
│   ├── class-scanner.php
│   ├── class-exporter.php
│   ├── class-packager.php
│   ├── class-security-filters.php
│   └── scanners/
├── templates/
├── assets/
├── tests/
│   ├── mocks/
│   └── wordpress/
└── README.md

docs/
├── exporter-audit.md
└── verification/
    └── e1-verification-receipt.md

samples/
├── legacy-1-export.zip
└── legacy-1-export.zip.sha256
```

**Structure Decision**: Stabilize the existing plugin in place. Test-only WordPress
orchestration lives below `moltex_exporter/tests/wordpress`; evidence shared by later phases
lives at repository-level `docs/` and `samples/` as required by `moltex.md`.

## Phase 0: Research Decisions

See [research.md](./research.md). Decisions cover the PHP/Composer baseline, WordPress smoke
fixture, scanner/artifact inventory method, legacy fixture provenance, and receipt status model.

## Phase 1: Design and Contracts

See [data-model.md](./data-model.md), [contracts/evidence.md](./contracts/evidence.md), and
[quickstart.md](./quickstart.md). The design adds evidence contracts only; it does not change
the exporter bundle contract.

## Post-Design Constitution Re-check

PASS. The design introduces no third implementation, no target migration behavior, and no
silent verification skip. All externally sourced content remains untrusted and sanitized.
