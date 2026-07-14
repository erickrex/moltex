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
safety ceiling and writes `export_completeness.json`. Private content is excluded by default.

**Discovery sample** exports representative content for analysis only and cannot prove a
complete migration.

## Current legacy artifacts

- `site_blueprint.json` — site, theme, plugin, and content summary
- `content/{post_type}/{slug}.json` — structured public content records
- `export_completeness.json` and `migration_readiness.json` — counts and diagnostics
- `media/` and `media/media_map.json` — local media evidence
- `menus.json`, settings, widgets, forms, blocks, shortcodes, hooks, and taxonomy evidence
- `redirects_candidates.csv` and `schema_mysql.sql` when their scanners emit them
- `snapshots/`, theme, plugin, and registered asset trees

Some registered scanners currently return in-memory results without a dedicated legacy ZIP
file, including SEO, integration-manifest, page-composition, relationship, and field-usage
results. See `docs/exporter-audit.md`; E2 decides which become declared contract artifacts.

## Installation and use

1. Install and activate the plugin in WordPress.
2. Open **Moltex Exporter** in the administration area.
3. Select complete migration or discovery sample.
4. Keep private content disabled unless it is deliberately in scope.
5. Run the export and download the ZIP.
6. Review the ZIP for private content and sensitive data before sharing it.
7. Resolve blockers in `migration_readiness.json` before later harness intake.

## Privacy

Credentials, password material, sensitive options, sensitive metadata, and common PII fields
are filtered. Callback evidence uses logical paths instead of absolute server paths. Manual
review remains mandatory before sharing an export.

## Tests

The repository contains PHPUnit tests, standalone regressions, and a disposable WordPress
smoke fixture under `tests/`. See `tests/README.md` for exact E1 commands and the current
classified coverage status.
