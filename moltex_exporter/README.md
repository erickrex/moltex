# Moltex Exporter

Moltex Exporter is a read-only WordPress plugin that creates a privacy-filtered,
checksummed `moltex-export/1` evidence ZIP for later rebuilding as a Git-managed Astro
site. The exporter observes and packages WordPress; `moltex_harness` interprets the ZIP.

## Supported scope

The complete profile targets content-led brochure, corporate, blog, editorial, portfolio,
and Gutenberg-first sites. Ecommerce, memberships, communities, learning systems,
bookings, multisite, unknown plugins, and custom behavior require explicit review or a
readiness blocker. Elementor and Divi are explicitly unsupported for complete migration:
their active-plugin evidence produces a page-builder readiness blocker, and the harness also
checks exported post meta, shortcodes, and rendered markup. A builder is not supported until
it has its own accepted evidence model, adapter, fixtures, visual checks, and fallbacks.

## Install the release

Build or obtain `moltex-exporter-1.3.0.zip`, then use **Plugins → Add New → Upload Plugin**.
The release requires WordPress 5.9+, PHP 7.4+, JSON, and `ZipArchive`. After activation,
open **Moltex Exporter** and resolve every blocking preflight result.

Moltex suppresses the known obsolete `djamingo-exporter` admin menu when site-local legacy
code registers it. Only the `moltex-exporter` page produces the supported versioned
`moltex-export/1` bundle.

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
4. Keep HTML snapshots on **Bounded (recommended)**. This captures at most 12
   representative routes; use **All** only for targeted diagnostics.
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

The release captures the exporter-owned evidence needed for supported content-led sites.
Version 1.3.0 records inactive, removed, and unknown plugin residue in
`legacy_evidence_index.json`. It uses declarative storage signatures and public-content
relationships without loading inactive PHP. Referenced post meta and bounded, allowlisted
custom-table rows are retained; dormant custom tables are manifest-only, and unresolved or
oversized payloads are declared for downstream acquisition or operator review. Activation
status is evidence only: public reachability determines whether legacy data matters.
Repeated media bytes are stored once while every source URL remains in the media map. For
GeoDirectory galleries, the primary blueprint bundles featured images and records the remaining
public gallery images as deferred acquisition sources. The migration harness assigns every source
URL a stable local target; production output never depends on runtime hotlinks. Raw
plugin readmes and PHP templates are omitted because structured plugin, capability, and
theme evidence owns those migration decisions. GeoDirectory sites additionally export
privacy-filtered public listing fields, locations, gallery media, approved reviews, and
the public search/sort/tab configuration needed for explicit replacement decisions. The
harness owns normalization, automated
source screenshot capture, Astro generation, and verification. The WordPress user is
never asked to capture or upload screenshots.

Before `bundle.json` is finalized, Moltex scans every producer-created artifact for
credential signatures, privacy canaries, server paths, unsafe links, and executable PHP.
The checksum-bound `privacy-scan.json` receipt is the only source of a passing
`privacy.secret_scan` declaration.

## Development

The repository contains PHPUnit and standalone regressions, a synthetic contract fixture,
the immutable real Golden Export, and disposable WordPress integration environments. See
[`tests/README.md`](tests/README.md) and the verification receipts under
[`docs/verification`](../docs/verification/).
