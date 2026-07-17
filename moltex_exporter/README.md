# Moltex Exporter

Moltex Exporter is a read-only WordPress plugin that creates a privacy-filtered,
checksummed `moltex-export/1` evidence ZIP for later rebuilding as a Git-managed Astro
site. The exporter observes and packages WordPress; the future `moltex_harness` interprets
the ZIP. H1 has not yet proved that consumer handshake.

## Supported scope

The complete profile targets content-led brochure, corporate, blog, editorial, portfolio,
and Gutenberg-first sites. Ecommerce, memberships, communities, learning systems,
bookings, multisite, unknown plugins, and custom behavior require explicit review or a
readiness blocker.

## Install the release

Build or obtain `moltex-exporter-1.2.3.zip`, then use **Plugins → Add New → Upload Plugin**.
The release requires WordPress 5.9+, PHP 7.4+, JSON, and `ZipArchive`. After activation,
open **Moltex Exporter** and resolve every blocking preflight result.

If wp-admin still shows a separate AI-branded export menu, deactivate and remove that
legacy plugin installation. It is not the Moltex Exporter release and does not produce the
versioned `moltex-export/1` bundle.

Do not upload a ZIP of the development directory: it contains tests, fixtures, and PHPUnit.
The supported release is built from a clean commit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File moltex_exporter/tools/build-release.ps1
```

Pilot on a staging clone before production.

## Export and validate

1. Select **Complete migration**.
2. Keep private content disabled for a public rebuild.
3. Confirm the complete-export ceiling is above every eligible post-type count.
4. Keep HTML snapshots enabled.
5. Export and download the signed ZIP.
6. Review `migration_readiness.json`, `export_completeness.json`, `error_log.json`, and the
   privacy state in `bundle.json`.
7. Validate outside WordPress:

   ```bash
   php tools/validate-bundle.php path/to/export.zip
   ```

Complete mode exports every eligible published item up to the configured per-type safety
ceiling. Discovery mode is representative evidence only and is never complete-migration
eligible. The package refuses to offer a download unless its schema, checksums, sizes, and
inventory validate.

## Privacy and limitations

Credentials, password material, sensitive options and metadata, common PII, and private
content are filtered or excluded by default. Manual review is still mandatory before a ZIP
is shared. Forms, shortcodes, hooks, external APIs, authentication, redirects,
accessibility, SEO, and visual parity can require explicit downstream decisions.

The release captures all exporter-owned evidence for supported content-led sites. It does
not claim that an arbitrary site can already be rebuilt; H1 must prove intake, and later
harness phases own normalization, automated source screenshot capture, Astro generation,
and verification. The WordPress user is never asked to capture or upload screenshots.

## Development

The repository contains PHPUnit and standalone regressions, a synthetic contract fixture,
the immutable real Golden Export, and disposable WordPress integration environments. See
[`tests/README.md`](tests/README.md) and the verification receipts under
[`docs/verification`](../docs/verification/).
