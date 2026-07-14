# Moltex Exporter Phase E1 Audit

**Audit date**: 2026-07-14
**Source of truth**: executable registry and write/copy sites in `moltex_exporter/`
**Bundle label**: `legacy-1` (current unversioned behavior; not `moltex-export/1`)

## Executive summary

The exporter registers 33 scanners. Fourteen are required for the hackathon's conservative
static-Astro migration profile, fourteen provide optional evidence, three are diagnostic,
and two are excluded from the profile because their database breadth is sensitive and
unbounded. “Excluded” is a product disposition, not a claim that E1 removed the current
scanner from the runtime; E2 owns enforcement of the published bundle contract.

The current ZIP is producer-driven rather than manifest-driven. The exporter writes a core
set of JSON/CSV/SQL patterns, while theme, plugin, media, snapshot, and asset scanners copy
dynamic trees. Several registered scanners return results without any dedicated legacy file;
that gap is recorded below rather than inventing an artifact.

## Scanner classification (33 registered scanners)

| Registry key | Class / priority | Disposition | Intended harness consumer | Rationale |
|---|---|---|---|---|
| `site` | `Site_Scanner` / 10 | required | intake + canonical site contract | Core site identity, types, taxonomies, and counts. |
| `theme` | `Theme_Scanner` / 20 | required | scaffold + presentation evidence | Theme files, templates, styles, and hierarchy establish the visual baseline. |
| `plugins` | `Plugin_Scanner` / 30 | required | capability contract | Active plugin inventory and behavioral fingerprints drive capability decisions. |
| `content` | `Content_Scanner` / 40 | required | conversion + route contract | Public posts/pages/CPT records and completeness are the migration payload. |
| `taxonomies` | `Taxonomy_Scanner` / 50 | required | canonical taxonomy contract | Terms and relationships are required content structure. |
| `media` | `Media_Scanner` / 60 | required | asset contract | Referenced media bytes and the source-to-export map are required assets. |
| `settings` | `Settings_Scanner` / 70 | required | canonical site/SEO defaults | Public site configuration affects generated behavior. |
| `menus` | `Menu_Scanner` / 80 | required | navigation contract | Primary navigation must be reconstructed. |
| `widgets` | `Widget_Scanner` / 90 | optional evidence | capability contract | Useful legacy layout evidence; not all widgets have a static consumer. |
| `user_roles` | `User_Roles_Scanner` / 100 | optional evidence | capability contract | Role shape can reveal unsupported workflows; no user accounts are migrated. |
| `site_options` | `Site_Options_Scanner` / 110 | optional evidence | canonical settings evidence | Privacy-filtered options aid interpretation but are not accepted blindly. |
| `acf` | `ACF_Scanner` / 115 | optional evidence | field/capability contract | Required only when ACF is present and consumed. |
| `shortcodes` | `Shortcode_Scanner` / 120 | optional evidence | conversion blockers | Identifies content constructs requiring replacement. |
| `forms` | `Forms_Scanner` / 125 | optional evidence | capability contract | Configuration is useful; submissions and PII are excluded. |
| `hooks` | `Hooks_Scanner` / 130 | diagnostic only | none | Runtime hook inventory is large and implementation-centric, not migration input. |
| `assets` | `Assets_Scanner` / 132 | optional evidence | asset/presentation evidence | Useful for visual reconstruction but size scales with registered assets. |
| `page_templates` | `Page_Templates_Scanner` / 135 | optional evidence | scaffold planning | Template assignments refine layout choices. |
| `block_patterns` | `Block_Patterns_Scanner` / 140 | optional evidence | conversion evidence | Reusable patterns may affect conversion, but are not required on every site. |
| `rest_api` | `REST_API_Scanner` / 145 | optional evidence | capability contract | Reveals dynamic integrations; callback paths must be sanitized. |
| `redirects` | `Redirects_Scanner` / 150 | required | redirect contract | Existing redirects must be preserved when present. |
| `database` | `Database_Scanner` / 155 | excluded | none | Raw schema breadth exposes server/plugin details and lacks a direct H1 consumer. |
| `translations` | `Translation_Scanner` / 160 | optional evidence | route/content contract | Required only for multilingual sources. |
| `environment` | `Environment_Scanner` / 165 | diagnostic only | intake diagnostics | Versions/extensions help explain an export but must not drive target behavior. |
| `content_relationships` | `Content_Relationships_Scanner` / 170 | required | canonical relationship contract | Links parentage, references, and related content. |
| `field_usage` | `Field_Usage_Scanner` / 175 | optional evidence | field contract | Supports evidence-based field decisions. |
| `plugin_instances` | `Plugin_Instances_Scanner` / 180 | optional evidence | capability contract | Instance configuration is useful only for supported plugins. |
| `page_composition` | `Page_Composition_Scanner` / 185 | required | conversion + visual contract | Page-level blocks/templates establish composition. |
| `seo_full` | `Seo_Full_Scanner` / 190 | required | SEO contract | Page metadata and canonical directives must survive migration. |
| `editorial_workflows` | `Editorial_Workflows_Scanner` / 195 | optional evidence | capability contract | Flags workflows that a static target may not implement. |
| `plugin_table_exports` | `Plugin_Table_Exports_Scanner` / 200 | excluded | none | Table contents are unbounded, commonly private, and have no declared consumer. |
| `search_config` | `Search_Config_Scanner` / 205 | required | capability/search contract | Search behavior needs an explicit preserve/replace decision. |
| `integration_manifest` | `Integration_Manifest_Scanner` / 210 | optional evidence | capability contract | Summarizes integrations but does not replace primary evidence. |
| `migration_readiness` | `Migration_Readiness_Scanner` / 220 | diagnostic only | planning diagnostics | Qualification summary is useful to humans; canonical contracts remain authoritative. |

Counts: required 14, optional evidence 14, diagnostic only 3, excluded 2; total 33.

## Artifact classification

All rows describe current `legacy-1` behavior. JSON files use ad hoc `schema_version: 1`
where the writer injects it; there is no bundle-level schema or manifest until E2.

| ZIP-relative path or pattern | Producer | Privacy | Size risk | Condition | Intended consumer |
|---|---|---|---|---|---|
| `site_blueprint.json` | `Exporter::create_blueprint` | filtered aggregate | content-scaled | always after results | intake/raw evidence |
| `site_settings.json` | settings → exporter | filtered | bounded | settings result | site contract |
| `menus.json` | menus → exporter | public | content-scaled | menus result | navigation contract |
| `widgets.json` | widgets → exporter | PII-sanitized | content-scaled | widgets result | capability evidence |
| `user_roles.json` | user roles → exporter | role names only; review | bounded | user roles result | capability evidence |
| `site_options.json` | site options → exporter | sensitive-filtered | option-scaled | site options result | settings evidence |
| `acf_field_groups.json` | ACF → exporter | configuration | plugin-scaled | ACF result | field contract |
| `shortcodes_inventory.json` | shortcodes → exporter | logical callback paths | registry-scaled | shortcode result | conversion blockers |
| `forms_config.json` | forms → exporter | submission/PII-filtered | plugin-scaled | forms result | capability evidence |
| `hooks_registry.json` | hooks → exporter | logical callback paths | potentially unbounded | hooks result | diagnostic only |
| `page_templates.json` | page templates → exporter | public configuration | bounded | result exists | scaffold evidence |
| `block_patterns.json` | block patterns → exporter | content-sanitized | content-scaled | result exists | conversion evidence |
| `rest_api_endpoints.json` | REST API → exporter | logical callback paths | endpoint-scaled | result exists | capability evidence |
| `redirects_candidates.csv` | redirects scanner | public URLs; review queries | route-scaled | redirects found/writer succeeds | redirect contract |
| `schema_mysql.sql` | database scanner | sensitive structural detail | database-scaled | schema access/writer succeeds | excluded/no consumer |
| `translations.json` | translations → exporter | public configuration | content-scaled | translation result | route/content contract |
| `site_environment.json` | environment → exporter | diagnostic; path review | bounded | environment result | diagnostics |
| `plugin_behaviors.json` | plugin scanner → exporter | configuration | plugin-scaled | behavior fingerprints exist | capability contract |
| `plugins_fingerprint.json` | plugin scanner → exporter | configuration | plugin-scaled | feature data exists | capability contract |
| `blocks_usage.json` | content → exporter | aggregate public data | bounded | block usage exists | conversion planning |
| `export_completeness.json` | content → exporter | counts/status | bounded | completeness exists | verification contract |
| `migration_readiness.json` | readiness → exporter | aggregate diagnostic | bounded | readiness result | diagnostics |
| `content/{post_type}/{slug[-id]}.json` | content → exporter | public content; meta filtered | content-scaled | eligible content by mode | conversion/routes |
| `snapshots/{slug}.html` | content scanner | sanitized rendered public HTML | content-scaled | snapshots enabled | visual/conversion evidence |
| `media/media_map.json` | media scanner | source URLs reviewed | media-scaled | media scan | asset contract |
| `media/{bounded relative path}` | media scanner | public media bytes | media-scaled | referenced/copyable media | asset contract |
| `error_log.json` | exporter | diagnostic; messages sanitized | bounded by errors | errors or warnings exist | verification diagnostics |
| `theme/style.css`, `theme/theme.json`, `theme/functions.php` | theme scanner | source code | theme-scaled | file exists | presentation evidence |
| `theme/templates/{relative}.html` | theme scanner | source templates | theme-scaled | block templates exist | scaffold evidence |
| `theme/parts/{relative}.html` | theme scanner | source templates | theme-scaled | template parts exist | scaffold evidence |
| `theme/parent/{style.css,theme.json,functions.php}` | theme scanner | source code | theme-scaled | child theme has parent files | presentation evidence |
| `theme/template_hierarchy.json` | theme scanner | configuration | bounded | theme scan | scaffold evidence |
| `theme/theme_mods.json` | theme scanner | sensitive-filtered settings | option-scaled | mods encode/write | presentation evidence |
| `theme/custom_css.css`, `theme/global_styles.json` | theme scanner | public presentation | content-scaled | configured | presentation evidence |
| `theme/css/{source}.css`, `theme/css_sources.json` | theme scanner | public presentation | asset-scaled | CSS sources discovered | presentation evidence |
| `theme/editor_settings.json` | theme scanner | public configuration | bounded | editor settings available | presentation evidence |
| `theme/rendered_css/{handle}.css`, `theme/rendered_css/manifest.json` | theme scanner | public presentation | asset-scaled | registered styles render | visual evidence |
| `assets_manifest.json` | theme scanner | logical asset inventory | asset-scaled | manifest write succeeds | asset contract |
| `assets/{js,css}/{sanitized filename}` | assets scanner | third-party/public assets | potentially unbounded | registered local assets | visual evidence |
| `plugins/readmes/{plugin}_readme.{txt,md}` | plugin scanner | public documentation | plugin-scaled | readable README exists | capability evidence |
| `plugins/plugins_fingerprint.json` | plugin scanner | configuration | plugin-scaled | write succeeds | capability contract |
| `plugins/{custom_post_types,taxonomies,shortcodes,blocks,database_tables}.json` | plugin scanner | configuration; table names reviewed | plugin/database-scaled | write succeeds | capability evidence |
| `plugins/feature_maps/{plugin}.json` | plugin scanner | configuration | plugin-scaled | supported feature map | capability evidence |
| `plugins/templates/{plugin}/{relative template}` | plugin scanner | plugin source template | potentially unbounded | bounded extension/template allowlist | presentation evidence |
| `plugins/plugins_templates_manifest.json` | plugin scanner | logical inventory | plugin-scaled | template scan | capability evidence |

### Registered results without a dedicated legacy file

`content_relationships`, `field_usage`, `plugin_instances`, `page_composition`, `seo_full`,
`editorial_workflows`, `plugin_table_exports`, `search_config`, and `integration_manifest`
return scanner results but `class-exporter.php` does not write a dedicated file for them.
Some may be partially summarized in `site_blueprint.json`; H1 must not assume a filename.
E2 owns deciding which become declared artifacts.

## Executable coverage

- PHP 8.2.31 and Composer 2.10.2 are installed; PHPUnit 9.6.35 is locked.
- All four standalone regressions and the plugin entry-point syntax check pass at baseline.
- The previously undocumented PHPUnit suite initially executed 76 legacy tests. Its real run
  found 47 mock/bootstrap errors, five assertion failures, and nine risky tests; these are
  classified in the separate receipt and are not represented as passing coverage.
- The disposable WordPress 7.0.1 smoke fixture installs and activates the plugin, triggers
  authenticated AJAX scans, and exercises signed ZIP downloads.

## Complete versus discovery smoke comparison

| Measure | Complete | Discovery | Explanation |
|---|---:|---:|---|
| ZIP entries | 394 | 384 | Discovery omits sampled content/snapshots. |
| Content JSON records | 7 | 2 | Complete exported all fixture public posts/pages; discovery limits each built-in type to one. |
| HTML snapshots | 7 | 2 | Mirrors exported content selection. |
| Media files | 0 | 0 | The bounded fixture intentionally has no uploaded media. |
| Scanner errors | 0 | 0 | No scanner reported an error. |
| Scanner warnings | 2 | 2 | No redirect CSV or database schema was produced on the clean fixture. |

The accepted pair was generated at `2026-07-14T20:50:14Z` after privacy fixes. The complete
ZIP was frozen as the compatibility fixture.

## Privacy review

### Method

The candidate ZIP is inspected without extracting entries. Text-like entries below 5 MiB
are searched for the fixture's private-content marker, synthetic secret markers, fixture
administrator email, Windows drive paths, the container document root, and common credential
or PII forms. Content and option filters are also covered by focused tests.

### Findings

| Finding | Initial result | Disposition |
|---|---|---|
| Private post marker | 0 hits | PASS — private content disabled. |
| Synthetic post-meta API key | 0 hits | PASS — sensitive meta filtered. |
| Synthetic option token | 0 hits | PASS — sensitive option filtered. |
| Fixture admin email | 0 hits | PASS — user PII absent. |
| Windows absolute path | 0 hits | PASS. |
| `/var/www/html` server path | 1 hit in the first `plugins/shortcodes.json` | PASS after fix — callback paths are logical; final ZIP has 0 hits. |
| Nested/unprefixed PII keys | Unit regression reproduced two leaks | PASS after fix — recursive/canonical filtering passes 10 focused assertions. |

The final frozen ZIP passes `privacy_fixture_regression.php`. Generic example addresses
`example@example.com` and `email@example.com` occur in WordPress core block-pattern examples;
they are public placeholders, not fixture or user PII.

No real production data was used. The source includes only explicit synthetic markers so a
negative privacy check cannot pass accidentally.

## Known limitations and E2 dependencies

> E2 status (2026-07-14): these dependencies were resolved by `moltex-export/1`, the
> declarative artifact registry, shared metadata policy, validated writer, checked-in
> schemas, deterministic `bundle.json`, and standalone ZIP validator. This section remains
> the E1 audit record; see `docs/export-bundle-contract.md` and the E2 receipt for the
> enforced contract.

- Asset breadth is large (hundreds of WordPress core CSS/JS entries even on the fixture) and
  is not bounded by the legacy format.
- Redirect/database scanners warn when their side files are absent instead of expressing a
  manifest-level optional/required disposition.
- Duplicate fingerprint artifacts exist at root and under `plugins/`.
- Several registered scanner results have no dedicated file.
- E2 must publish the actual required set, bounds, schemas, checksums, and standalone validator;
  this audit intentionally does not implement that contract.
