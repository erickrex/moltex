# Review of exporter changes against missing artifacts

## Scope and verdict

Reviewed the uncommitted changes, including new untracked implementation and test
files, in `moltex_exporter/` against `missing_artifacts_from_wp_client.md`.
`moltex_harness` was excluded from the review.

**The changes do not solve all of the documented gaps.** They add substantial
coverage, but blocking omissions and archive-packaging failures remain. Passing
unit tests do not establish that a fresh client export contains every requested
artifact.

No implementation changes were made during the review. This file records its
findings.

## Findings

### 1. [P1] Archive splitting rejects valid entry coverage — M1/X3

- Source: `moltex_exporter/includes/class-packager.php`, lines 320–321.
- The coverage check compares ordered arrays of filenames. Splitting moves
  non-media entries before media entries, so a source ZIP containing content,
  media, then more data fails even when every file was copied exactly once.
- Reproduced with entries in this order: `content/a.json`, `media/a.jpg`,
  `site_settings.json`, `bundle.json`. Splitting raised
  `ZIP parts do not cover the validated bundle exactly`.
- Consequence: an export exceeding the part-size threshold can fail packaging
  despite having complete, correctly copied contents.
- Required correction: compare filename sets independently of order while still
  checking exact coverage and duplicates. Add a regression with interleaved media
  and non-media entries.

### 2. [P1] Archive snapshot routes never receive their inputs — S1

- Source: `moltex_exporter/includes/scanners/class-content-scanner.php`,
  lines 104–106.
- Snapshot generation runs before `post_type_inventory` is populated.
  `content_data` also never contains the taxonomy scanner results consumed by the
  route planner.
- Reproduced through a normal content scan: the additional planned route kinds
  were only `home`, `search`, and `not_found`. Supplying the returned inventory to
  the route planner afterward added post-type archive routes.
- Consequence: the new planner does not capture post-type and term archives in
  the normal scan flow. Location-archive evidence also remains incomplete.
- Required correction: populate the inventory first and supply taxonomy/location
  evidence before planning snapshots. Test the complete scan flow, not only the
  route helper in isolation.

### 3. [P1] GeoDirectory category metadata still has no reader — C4/M4

- Source: `moltex_exporter/includes/scanners/class-media-scanner.php`,
  lines 222–226.
- The new media discovery consumes term metadata from the existing taxonomy
  scanner. That scanner reads only WordPress `get_term_meta()`.
- Nothing reads the separate `wp_geodir_term_meta` table identified in the gap
  document, which reports 28 rows.
- Consequence: icons, colours, descriptions, and marker images stored exclusively
  in that table remain absent. Adding `taxonomies.json` does not by itself close
  this gap.
- Required correction: export and merge the GeoDirectory term records before
  discovering their referenced media. Test records that exist only in the
  plugin-owned table.

### 4. [P2] Archive parts can exceed the upload limit — M1/X3

- Source: `moltex_exporter/includes/class-packager.php`, lines 307–315; grouping
  occurs earlier in `split_into_parts()`.
- Grouping uses uncompressed file sizes without accounting for ZIP overhead.
  Oversized individual files are retained, and all non-media data goes into one
  unlimited data part. Oversized results are merely flagged.
- Reproduced with two random payloads of 4,000 and 4,500 bytes and an 8,500-byte
  limit: the resulting media part was 8,726 bytes and had `over_limit: true`, even
  though neither input file exceeded the limit.
- Consequence: the resulting parts are not guaranteed to fit the requested
  upload limit.
- Required correction: enforce the final archive size and explicitly handle
  oversized individual files and oversized data parts.

### 5. [P2] Field reconciliation counts only retained definitions — C2

- Source: `moltex_exporter/includes/scanners/class-content-scanner.php`,
  lines 1035–1039; definition filtering occurs around lines 1077–1080.
- `field_summary.source_rows` counts `all_fields` after rows with an empty
  `htmlvar_name` or an unmatched post type have already been discarded without a
  reason.
- Reproduced with eight source definition rows, including an active fieldset row
  with an empty `htmlvar_name`: the reported source count was seven.
- Consequence: the export cannot account for every source row as requested, so
  it cannot establish that the original 121-versus-96 discrepancy is resolved.
- Required correction: preserve those rows as diagnostic definitions or report
  their IDs and exclusion reasons against the actual source count.

### 6. [P2] Story media stored in postmeta is skipped — C8

- Source: `moltex_exporter/includes/scanners/class-media-scanner.php`,
  lines 190–199.
- Opting `wp_story` into content export does not ensure that its media is
  collected. The finder walks HTML and GeoDirectory-specific sections, but never
  ordinary `content_item.postmeta`, where the gap document identifies story data
  as a likely source.
- Reproduced with a story containing a video URL in postmeta and empty HTML: the
  media scan produced zero entries.
- Consequence: stories can be exported as content records while their media
  files remain missing.
- Required correction: discover media in filtered story metadata and preserve
  the owning post and field references.

### 7. [P2] Compiled translation overrides disappear — F3

- Source: `moltex_exporter/includes/scanners/class-translation-scanner.php`,
  lines 119–122.
- The translation scan accepts only `.po` files. A custom override available only
  as `.mo` is silently omitted.
- Reproduced with a directory containing only an `.mo` file: the scan returned
  zero translation artifacts.
- Consequence: the implementation does not capture every custom translation file
  requested by F3.
- Required correction: capture compiled custom translations as well, or decode
  them into equivalent exported entries.

## Additional incomplete requirements

| Gap | Remaining limitation |
|---|---|
| S1 | There are no screenshots or rendering at 390, 768, and 1440 px. The snapshot manifest merely declares that an external headless renderer is required. Profile and compare routes are also missing. |
| S4 | Kadence collection reads existing caches and files; it does not capture generated CSS for every post. |
| M2 | Video discovery improves, but duration and dimensions depend on existing WordPress attachment metadata. Unregistered videos lack that metadata, and video-to-poster relationships are not explicitly exported. |
| F1 | Forminator integration configuration is reduced to integration names, losing destination details needed to reconstruct it. |

Relevant implementation locations:

- S1: `moltex_exporter/includes/scanners/class-content-scanner.php`,
  `build_snapshot_route_plan()` and `write_snapshot_manifest()`.
- S4: `moltex_exporter/includes/scanners/class-assets-scanner.php`,
  `build_kadence_css_inventory()`.
- M2: `moltex_exporter/includes/scanners/class-media-scanner.php`,
  `generate_media_map()` and `get_attachment_metadata()`.
- F1: `moltex_exporter/includes/scanners/class-forms-scanner.php`,
  `export_forminator()`, particularly the `array_keys()` conversion of
  integration configuration around line 791.

## Coverage of every documented gap

“Implemented” below means the code adds the relevant collection mechanism. It
does not mean the mechanism has been verified against the client's live
WordPress installation or a fresh client export.

| Gap | Review result |
|---|---|
| M1 | Partial: gallery bundling improves, but archive splitting has the failures in findings 1 and 4. |
| M2 | Partial: video discovery improves; metadata and explicit poster relationships remain incomplete. |
| M3 | Implemented: site-logo, site-icon, and theme-setting media discovery. |
| M4 | Partial: marker discovery cannot consume metadata stored only in `wp_geodir_term_meta`; see finding 3. |
| M5 | Implemented: attachment alt text, fallback handling, and provenance. |
| C1 | Implemented with operator choices: excluded-field definitions, configurable inclusion of values, and email-presence flags. Public visibility and continued paid-tier requirements still need client decisions. |
| C2 | Partial: richer definitions are exported, but source-row reconciliation remains incomplete; see finding 5. |
| C3 | Implemented: diagnostics and warnings for populated columns without matching definitions. |
| C4 | Partial: taxonomy evidence is emitted, but the separate GeoDirectory term-metadata table remains unread; see finding 3. |
| C5 | Implemented: rating criteria, styles, review approval information, image references, and review reconciliation. |
| C6 | Implemented: location-table records and additional listing location/address fields. |
| C7 | Implemented: complete sort-row evidence, advanced-search settings, and search placements. |
| C8 | Partial and opt-in: non-public story posts can be included, but postmeta-only media is missed; see finding 6. Whether stories remain is a client decision. |
| C9 | Implemented: site GMT offset and timezone plus business-hours timezone parsing. |
| C10 | Implemented: nested postmeta diagnostics and removal of legacy gallery strings from the handled fields. |
| S1 | Incomplete: archive inputs are missing in the scan flow, viewport rendering and PNG capture are absent, and route coverage remains incomplete. |
| S2 | Implemented: font inventory and collection from the supported local font directories. |
| S3 | Implemented: Popup Maker themes and popup settings, including triggers, cookies, and conditions. Whether the popup remains is a client decision. |
| S4 | Partial: cached CSS collection exists, but per-post generated CSS capture is incomplete. |
| F1 | Partial: Forminator definitions are collected, but integration destination configuration is discarded. |
| F2 | Implemented: full Redirection rules, groups, statuses, and aggregated 404 evidence. |
| F3 | Partial: `.po` overrides are parsed, but `.mo`-only overrides are omitted; see finding 7. |
| F4 | Implemented: Code Snippets are exported for review with credential redaction and an explicit instruction never to execute them. |
| F5 | Implemented with opt-in: MailPoet lists/counts and optional subscriber export. Client agreement is still required for subscriber data. |
| U1 | Implemented with opt-in for emails: stable users, roles, ownership mappings, and reviewer counts, without passwords. |
| U2 | Implemented: UsersWP form fields, profile tabs, sorting, and filtered settings. |
| X1 | Client responsibility: the production-origin setting records an operator declaration; the client must still confirm the production domain. |
| X2 | Client responsibility: adult-consent evidence and policy cannot be supplied by the exporter. |
| X3 | Partial: bundle validation addresses declared-file hygiene, but upload-sized archive parts are not reliable; see findings 1 and 4. |

## Client decisions still required

The source document explicitly identifies these as outside the exporter's
ability to resolve independently:

1. Confirm the production domain (X1).
2. Confirm whether `precio_por_hora` and the featured flag show publicly (C1).
3. Decide whether stories and the subscription popup remain (C8, S3, F1).
4. Agree to the export of user emails and subscribers before enabling those
   options (U1, F5).
5. Supply the adult-consent evidence and policy (X2).

## Validation and limits

- PHPUnit passed using PHP in the available `wordpress:php8.3-apache` Docker
  image: **196 tests, 2,225 assertions**. The successful run included the
  checked-in sample and Golden Export fixtures mounted read-only.
- PHP syntax checks passed for the exporter `includes/` and `tests/` trees.
- `git diff --check -- moltex_exporter` passed.
- Standalone content-export, sample-scope, export-directory, identity,
  privacy-fixture, and callback-path regressions reported success.
- The standalone inventory audit fails on an unchanged mismatch: it expects
  33 scanners and finds 34. This was not identified as a regression introduced by
  the reviewed changes.
- Targeted checks reproduced the archive-order failure, missing archive routes,
  inaccurate field-row count, skipped story media, omitted `.mo` files, and an
  archive part exceeding its configured size limit.
- No live WordPress/client export was validated. Plugin-specific database
  compatibility and actual completeness of the client's next export remain
  unverified.

## Resolution (2026-10-25)

All seven findings and the four additional limitations were addressed in
`moltex_exporter/`, each with a regression test. PHPUnit (PHP 8.4 in Docker):
206 tests, 2,378 assertions, no failures.

| Item | Change | Test |
|---|---|---|
| 1 | Part coverage is compared as sorted name lists, so entry order no longer matters and duplicates still fail. | `PackagerContractTest::test_interleaved_media_and_data_entries_are_covered` |
| 4 | Grouping uses compressed size plus ZIP overhead; every written part is measured and bisected while over the limit. Data is split into `data`, `data-02`, … like media. A single entry larger than the limit is cut into `<part>.zip.001`, `.002`, … byte chunks, so no download exceeds the limit. | `test_part_archives_stay_under_limit_including_zip_overhead`, `test_oversized_data_is_split_into_several_data_parts` |
| 2 | `post_type_inventory` is built before snapshots. The planner looks up one non-empty term per taxonomy itself, and adds pages assigned in `geodir_settings` / `uwp_settings` (`page_*`, `*_page`), which covers compare, favourites and profile. | `SnapshotRoutePlanTest::test_full_scan_plans_archive_term_and_plugin_page_routes` |
| 3 | The taxonomy scanner reads `wp_geodir_term_meta`, attaches rows to terms as `geodir_meta`, and reconciles them in `taxonomies.json` → `geodir_term_meta`. The media scanner scans both attached and unattached rows. | `TaxonomyScannerTest::test_geodir_term_meta_rows_are_attached_and_reconciled`, `MediaScannerTest::test_marker_stored_only_in_geodir_term_meta_is_collected` |
| 5 | Rows without `htmlvar_name` are kept as `unkeyed_rows` and counted in `source_rows`. The new `field_reconciliation` accounts for every table row, including rows of post types that were not exported. | `ContentScannerTest::test_geodirectory_configuration_lists_every_field_row_with_disposition` |
| 6 | The media scanner scans each item's filtered `postmeta`. | `MediaScannerTest::test_story_video_in_postmeta_only_is_collected` |
| 7 | `.mo` files are decoded. A `.mo` beside its `.po` is skipped as the compiled copy. | `TranslationFilesTest::test_compiled_only_override_is_decoded` |
| M2 | Unregistered MP4/MOV videos get `length`, `width` and `height` from the container header. `<video poster>` pairs are recorded as `poster` / `poster_for`. | `test_unregistered_video_gets_container_details_and_poster_link` |
| S4 | Inline Kadence styles in each saved detail snapshot are written to `assets/kadence-css/rendered/post-<id>.css`, with `rendered_coverage` counts. | `KadenceCssInventoryTest::test_render_time_css_is_taken_from_saved_detail_snapshots` |
| F1 | `integration_settings` keeps destination details. Credential-like keys and webhook URLs are replaced with `[REDACTED]`. | `FormsForminatorTest` |

Also fixed: `DownloadStreamingTest` failed on PHP 8.4 because of an implicit nullable
parameter deprecation in the bundle validator and artifact writer constructors.

Still open:

- S1 PNG screenshots at 390/768/1440 px need a headless browser. PHP cannot render them.
- S4 render-time CSS covers only posts that have a snapshot. Every post needs `html_snapshot_mode` `all`.
- `tests/audit_inventory_regression.php` expects 33 scanners and finds 34. The scanner registry in `includes/class-scanner.php` is unchanged from the last commit, so these changes did not cause it.
- No live WordPress export was run.
