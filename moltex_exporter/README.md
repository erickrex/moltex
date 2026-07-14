# Moltex Exporter

Moltex Exporter is a WordPress plugin that creates the local evidence bundle consumed by
`moltex_harness` to rebuild a content-led site as a Git-managed Astro repository with
bounded Codex Desktop tasks and independent verification.

It is read-only: it does not modify WordPress content or configuration.

## Supported scope

The first complete-migration profile targets:

- Brochure and corporate sites
- Blogs and basic editorial sites
- Portfolios
- Gutenberg-first content sites
- Basic forms and integrations that can be reviewed and replaced explicitly

The exporter records a blocking readiness result for known complex site
classes such as ecommerce, memberships, communities, learning-management
systems, booking applications, and WordPress multisite. Unknown plugins and
custom behavior still require manual review.

## Export modes

### Complete migration

Exports every eligible published content item for each supported post type,
up to the configured per-type safety ceiling. It generates
`export_completeness.json`, which compares discovered and exported counts.
`moltex_harness` refuses a complete-migration bundle that does not prove completeness.

Private content is excluded by default to prevent accidental disclosure when a
site is later published publicly. It may be enabled explicitly for a controlled
migration.

### Discovery sample

Exports representative content for analysis only. Discovery bundles cannot
pass the complete-migration qualification gate.

## Important artifacts

- `site_blueprint.json` — site, theme, plugin, and content summary
- `content/{post_type}/{slug}.json` — one structured record per content item
- `export_completeness.json` — discovered/exported counts and exclusions
- `migration_readiness.json` — target eligibility and blockers
- `media/` and media maps — local media evidence
- `menus.json` — navigation structure
- `seo_full.json` — SEO evidence
- `redirects_candidates.csv` — legacy redirect candidates
- `forms_config.json` — supported form definitions
- `integration_manifest.json` — external integration inventory
- `snapshots/` — optional rendered reference pages
- theme, block, shortcode, hook, taxonomy, and field-usage artifacts

## Installation and use

1. Install and activate the plugin in WordPress.
2. Open **Moltex Exporter** in the WordPress administration area.
3. Select **Complete migration**.
4. Keep private content disabled unless it is intentionally in scope.
5. Run the export and download the ZIP.
6. Open the ZIP with the local `moltex_harness` project.
7. Resolve any blockers in `migration_readiness.json`.

## Privacy

Credentials, password material, sensitive options, and sensitive metadata are
filtered. Always inspect an export before sharing it with another person or
publishing reconstructed content.

## Tests

The repository contains PHPUnit-style tests and standalone regression scripts
under `tests/`.
