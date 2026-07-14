# Phase E2 Verification Receipt

**Phase**: E2 — Publish and enforce the Moltex export contract  
**Date**: 2026-07-14  
**Contract**: `moltex-export/1`  
**Exporter version**: 1.1.0  
**Status**: ACCEPTED

## Environment

The reference run used the repository's PHP 8.2/WordPress 7.0.1 Docker image because PHP
was not present on the current host PATH. The installed locked suite is PHPUnit 9.6.35.
The live fixture used WordPress 7.0.1, PHP 8.2, MariaDB 10.11.8, and WP-CLI 2.10.0.

## Executable evidence

| Check | Status | Result |
|---|---|---|
| Changed PHP syntax | PASS | Registry, schema validator, writer, ZIP validator, exporter, packager, scanners, tests, plugin entry point, and CLI reported no syntax errors |
| PHPUnit | PASS | 93 tests, 309 assertions, 0 errors, 0 failures, 0 risky tests |
| Per-item export regression | PASS | Required artifacts finalized; duplicate slug preserved with stable source-ID suffix |
| Synthetic sample validator | PASS | 24 ZIP entries; no warnings or errors; complete-migration eligible |
| Sample bundle ID | PASS | `sha256:885f38ea7128955317552ee95c85a2a976cd7a72d4ee9b82f24205db76870d8b` |
| Sample ZIP SHA-256 | PASS | `7e692af910f46bbf7f60b2412b2fe7d5f34878c11772ebc19d3d1e0422c0b2e6` |
| WordPress complete export | PASS | 7 content JSON, 7 snapshots, 0 scanner errors, 2 classified optional-file warnings |
| Complete ZIP validation | PASS | 393 inventoried artifacts; `sha256:db4bd6837c0d68264d805d1d4d2759814c40f551a5af2d903bb05cebab644109`; complete-migration eligible |
| WordPress discovery export | PASS | 2 content JSON, 2 snapshots, 0 scanner errors, 2 classified optional-file warnings |
| Discovery ZIP validation | PASS | 384 inventoried artifacts; `sha256:a8c5889019a375c0148abff6b5c8d2cdd97e6e0fb5e56d68fb7982b1899c1eae`; valid evidence and not complete-migration eligible |
| Disposable cleanup | PASS | WordPress/MariaDB containers, network, and both named volumes removed |

The two scanner warnings in each live export are the already classified absence of optional
`redirects_candidates.csv` and `schema_mysql.sql` on the clean fixture.

An initial smoke attempt inherited a named WordPress volume and stale host URL after an
interrupted process. The fixture now resets `home`/`siteurl` on every setup and uses
`docker compose down --volumes`; the final recorded run began with a fresh database and
removed all disposable state.

## Contract and negative cases

The executable suite covers:

- the reviewed pre-writer required-path and semantic-key characterization fixture;
- registry completeness and path normalization;
- deterministic manifests and equivalent normalized identities;
- schema rejection, malformed UTF-8, duplicate writes, atomic replace failure, producer
  context, required-file finalization failure, and packaging refusal;
- changed-byte checksum and schema localization, missing required artifacts, traversal,
  duplicate paths, size bounds, and direct ZIP validation without extraction;
- complete/discovery eligibility and reconciled post-type counts;
- shared option, post-meta, and term-meta privacy policy;
- static Astro eligibility and structured unsupported-site blockers; and
- a schema-valid stable validator report.

## Exit gate

| Gate | Status | Evidence |
|---|---|---|
| Unchanged fixture exports have equivalent normalized manifests | PASS | Deterministic two-directory writer test |
| Every required artifact has a schema or explicit non-JSON contract | PASS | Declarative registry and 13 checked-in schemas |
| Required JSON is declared once and uses the writer | PASS | Registry characterization and exporter boundary tests |
| Option, post-meta, and term-meta share one policy | PASS | Central security-filter implementation and regression coverage |
| ZIP proves inventory and integrity | PASS | Standalone validator passes synthetic and live bundles; tamper/missing cases fail |
| Complete/discovery and privacy semantics are executable | PASS | PHPUnit cases and final two-mode WordPress smoke |

**E2 acceptance**: ACCEPTED. E3 may now freeze the real sanitized Golden Path bundle; the
synthetic E2 sample is not a substitute for that real-site acceptance fixture.
