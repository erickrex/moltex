# Moltex Exporter

Moltex Exporter is a read-only WordPress plugin that creates the local evidence bundle a
later `moltex_harness` phase will consume to rebuild a content-led site as a Git-managed
Astro repository. It does not modify WordPress content or configuration.

## Supported scope

The complete-migration profile targets brochure, corporate, blog, editorial, portfolio,
and Gutenberg-first sites. Ecommerce, memberships, communities, learning management,
booking applications, multisite, unknown plugins, and custom behavior require explicit
review or a blocking readiness result.

## Export modes

**Complete migration** exports every eligible published item up to the configured per-type
safety ceiling and writes reconciled completeness counts. Private content is excluded by
default.

**Discovery sample** exports representative content for analysis. It is valid evidence but
cannot prove a complete migration.

## Versioned export contract

Version 1.1.0 emits `moltex-export/1` by default. `bundle.json` is the authoritative sorted
inventory and includes schemas, sizes, SHA-256 checksums, count/privacy semantics, and a
deterministic normalized bundle ID. Required JSON passes through the schema-validated atomic
writer; packaging refuses a missing or invalid contract.

Required evidence includes site blueprint/settings, menus, completeness, media map,
migration readiness, resolved SEO, forms, integrations, and every per-item content record.
Optional evidence remains declared and checksummed. See
[`docs/export-bundle-contract.md`](../docs/export-bundle-contract.md) for the exact boundary.

## Installation and use

1. Install and activate the plugin in WordPress.
2. Open **Moltex Exporter** in the administration area.
3. Select complete migration or discovery sample.
4. Keep private content disabled unless it is deliberately in scope.
5. Run the export and download the ZIP.
6. Review the ZIP for private content and sensitive data before sharing it.
7. Resolve blockers in `migration_readiness.json` before later harness intake.
8. Run `php tools/validate-bundle.php path/to/export.zip` outside WordPress.

## Privacy

Credentials, password material, sensitive options, post metadata, term metadata, and common
PII fields pass through the shared security policy. Callback evidence uses logical paths
instead of absolute server paths. Manual review remains mandatory before sharing an export.

## Tests

The repository contains PHPUnit tests, standalone regressions, an immutable synthetic
contract ZIP, the reviewed real WordPress Golden Export, and disposable WordPress fixtures
under `tests/`. See
`tests/README.md` for the exact commands and current classified coverage.
