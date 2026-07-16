# E3 Staging Pilot Runbook

1. Build `dist/moltex-exporter-1.2.0.zip` from a clean reviewed commit and retain its SHA-256
   receipt.
2. Restore a staging clone of the source site. Do not begin on production.
3. Upload and activate the release ZIP through WordPress, open Moltex Exporter, and resolve
   every blocking preflight result.
4. Capture representative public routes with the bundled Chromium helper. Upload and
   register the reviewed PNGs with their route and viewport.
5. Select complete mode, keep private content disabled, keep HTML snapshots enabled, and set
   the per-type ceiling above every eligible public count.
6. Export and download the signed ZIP. Do not edit it.
7. Run the bundled standalone validator outside WordPress.
8. Review completeness, readiness, errors/warnings, capabilities, screenshots, and privacy.
   Production use is accepted only when validation passes, counts reconcile, required media
   appears exactly once, visual evidence is present, blockers are empty, and the privacy
   review is signed.

This proves exporter operation only. H1 remains responsible for proving that
`moltex_harness` can consume the frozen contract without manual editing.
