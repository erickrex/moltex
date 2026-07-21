# Moltex Support and Readiness Report

This report is the concise operational companion to the authoritative support matrix in
[`moltex.md`](../moltex.md#authoritative-support-matrix). It describes the executable
classification boundary; it does not expand product scope.

## Readiness examples

| Evidence | Classification | Pipeline result |
|---|---|---|
| Complete public classic/Gutenberg site with standard content, media, navigation, SEO, and redirects | Supported | Eligible, subject to verifier and migration tasks |
| Static ACF values or the tested GeoDirectory public-listing subset | Supported within declared fields | Reproduced through typed contracts |
| Forms, custom shortcodes, integrations, or GeoDirectory discovery controls | Conditional | Blocking decision until a target disposition is recorded |
| Active Elementor/Elementor Pro or Divi Builder plugin | Unsupported page builder | Ineligible for complete migration |
| `_elementor_data`, `_elementor_edit_mode`, `_et_pb_use_builder`, or `_et_pb_old_content` post meta | Unsupported page builder | Ineligible even if plugin inventory is absent |
| Elementor rendered markers or Divi `[et_pb_*]`/rendered markers | Unsupported page builder | Ineligible even if plugin and post-meta evidence are absent |
| WooCommerce, membership/community, LMS, booking, transactional state, or multisite | Unsupported application | Ineligible for the static profile |
| Incomplete/discovery-only export | Incomplete evidence | Ineligible for complete migration |

## Why Elementor and Divi are blocked

Generic sanitized HTML is useful evidence but is not a deterministic page-builder adapter.
It does not prove responsive rules, global templates, dynamic widgets, theme-builder state,
or edit-time data survived. Moltex therefore emits an `unsupported_page_builder` error,
an evidence-linked capability and decision, and `static_eligibility: ineligible` instead of
claiming that a visually plausible fallback is complete.

Each builder needs a separate future phase with exporter evidence, canonical models,
conversion boundaries, representative fixtures, visual acceptance, negative mutations,
and fallback behavior.

## Current proof boundary

- Golden content-led export: immutable local fixture with intake, contract, generation,
  build, verifier, planning, mutation, and reproducibility coverage.
- Builder negatives: Elementor post-meta and Divi shortcode fixtures plus exporter active
  plugin tests.
- Release candidate: version comes from the plugin entry point; the release builder checks
  all declarations and emits a deterministic development-free ZIP receipt.
- Live WordPress minimum/reference smoke and a fresh real staging export remain release-time
  environment gates. They must be recorded from the exact candidate ZIP and may not be
  replaced by unit-test claims.
- Meganoche export `ef4cfeb7c421a72718be9d81a3de3ae96bb4689f6d8ab362313dbbd581bec7b3`
  was re-run on July 21, 2026. H1 accepted 478 files/44,434,799 expanded bytes and H2
  compiled 165 routes, 720 assets, and 30 capabilities. Elementor `_elementor_data`
  evidence was found on four routes, so the composed pipeline stopped deterministically at
  eligibility with exit 6/`static_ineligible` before browser access. This supersedes treating
  the earlier unexplained HTTP 500 routes as a successful migration; Meganoche now has an
  explicit unsupported-page-builder blocked report and is not a fresh supported-site proof.
