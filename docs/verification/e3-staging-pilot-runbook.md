# E3 Staging Pilot Runbook

1. Build `dist/moltex-exporter-1.2.4.zip` from a clean reviewed commit and retain its SHA-256
   receipt.
2. Restore a staging clone of the source site. Do not begin on production.
3. Upload and activate the release ZIP through WordPress, open Moltex Exporter, and resolve
   every blocking preflight result.
4. Select complete mode, keep private content disabled, keep HTML snapshots enabled, and set
   the per-type ceiling above every eligible public count.
5. Export and download the signed ZIP. Do not edit it.
6. Run the bundled standalone validator outside WordPress.
7. Review completeness, readiness, errors/warnings, capabilities, rendered HTML, and privacy.
   Source screenshots are captured automatically from the H2 visual capture plan before H3;
   the WordPress operator does not provide them.
   The exporter pilot passes when validation succeeds, counts reconcile, required media
   appears exactly once, blockers are empty, and the privacy review is signed. Full migration
   acceptance later requires the bundle-bound automated visual capture receipt.

This proves exporter operation only. H1 remains responsible for proving that
`moltex_harness` can consume the frozen contract without manual editing.
