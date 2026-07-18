=== Moltex Exporter ===
Contributors: moltex
Tags: migration, export, astro, static-site
Requires at least: 5.9
Tested up to: 7.0
Requires PHP: 7.4
Stable tag: 1.2.9
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Create a privacy-filtered, checksummed WordPress evidence ZIP for a verified static-site migration.

== Description ==

Moltex Exporter captures public content, referenced media, navigation, site/theme/plugin evidence,
resolved SEO, capabilities, readiness, and bounded rendered HTML in the versioned
moltex-export/1 contract.

The plugin is read-only with respect to WordPress content. It writes temporary export artifacts
under uploads and removes them according to the configured retention period.

== Installation ==

1. Upload the supported moltex-exporter release ZIP.
2. Activate Moltex Exporter.
3. Open Moltex Exporter in wp-admin and resolve blocking preflight results.
4. Pilot on a staging clone before production.

Moltex suppresses the known obsolete djamingo-exporter admin menu when site-local legacy
code registers it. Only the moltex-exporter page produces the supported moltex-export/1 bundle.

PHP ZipArchive is required. Complete exports exclude private content by default. Always review an
export for private material before sharing it.

== Frequently Asked Questions ==

= Does this rebuild the site? =

No. The plugin creates exporter-owned evidence. The separate Moltex harness will own intake,
normalization, Astro generation, and verification.

= Are all WordPress sites supported? =

No. Transactional, account-heavy, multisite, and unknown custom behavior can produce readiness
blockers or manual-review items.

== Changelog ==

= 1.2.9 =
* Stopped reporting intentionally absent optional redirect CSV and database schema SQL sidecars as export warnings.
* Kept genuine scanner, artifact-writer, and packaging failures in the export error log.

= 1.2.8 =
* Kept complete GeoDirectory gallery descriptors while bundling only featured gallery binaries in the primary blueprint.
* Added explicit bundled, deferred, and unavailable acquisition metadata with a local-only runtime policy.
* Added deterministic H1/H2 support for mapping every old media URL to a collision-safe local Astro asset destination.

= 1.2.7 =
* Added privacy-filtered GeoDirectory listing fields, locations, galleries, approved reviews, and public field definitions.
* Added GeoDirectory search, sort, and tab evidence for explicit Astro replacement decisions.
* Preserved GeoDirectory evidence through the Moltex H1 intake and H2 migration contracts.

= 1.2.6 =
* Limited rendered HTML evidence to 12 representative routes by default, with explicit off and all-content modes.
* Deduplicated byte-identical media while preserving every source URL in the media map.
* Replaced raw plugin readmes and PHP templates with the structured plugin and capability evidence used by the migration harness.

= 1.2.5 =
* Hardened large ZIP downloads against output-buffer and response-compression corruption.
* Limited packaged scripts and styles to public frontend assets and their dependency closure.

= 1.2.4 =
* Removed the obsolete djamingo-exporter admin menu when the supported Moltex Exporter is active.

= 1.2.3 =
* Added the Export blueprints submenu and explicit Astro rebuild wording.
* Removed false repeated execution-time warnings and kept bundled diagnostics aligned with the admin result.

= 1.2.2 =
* Removed WordPress screenshot collection; the planned harness will capture source visuals automatically between H2 and H3.

= 1.2.1 =
* Replaced obsolete AI-agent wording with the accurate Moltex Exporter and Export blueprint interface.

= 1.2.0 =
* Added release packaging, live-site preflight, reviewed screenshot management, and installable ZIP verification.

= 1.1.0 =
* Published and enforced the moltex-export/1 evidence contract and Golden Path fixture.
