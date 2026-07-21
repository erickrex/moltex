# Filter Out Inactive Plugin Baggage

## Status

Implemented in code for the primary blueprint in exporter 1.3.0 and the current
harness; a clean release build and staging-site export remain the live validation gate.
`moltex.md` owns the physical bundle contract; `moltex_harness.md` owns intake,
canonical classification, conversion, planning, and verifier behavior. Targeted
second-stage acquisition remains a declared follow-up after real 1.3.0 bundles prove
stable evidence IDs and reproducible relationship discovery.

## Goal

Reduce ZIP size and downstream noise caused by inactive, removed, or abandoned
WordPress plugins without losing data that still affects the public website.

The system must filter by observed use and public reachability, not merely by
WordPress activation state. Plugin activation is evidence, not a migration
decision.

## Current behavior

The exporter already avoids most bulky inactive-plugin material:

- It inventories every installed plugin with name, slug, version, and active
  status.
- It collects detailed behavioral fingerprints and active-plugin options only
  for active plugins.
- It does not package raw plugin PHP, readmes, or plugin templates.
- Registered CPTs, taxonomies, blocks, shortcodes, forms, and public assets are
  normally limited to active runtime registrations.
- Media packaging is limited to references discovered in exported public
  content.
- Supported plugin table-row exports are normally gated by active runtime APIs.

Residual evidence can still be retained:

- Every non-core WordPress table can appear in database schema/count metadata,
  including stale tables from inactive or removed plugins.
- Security-filtered postmeta is currently retained with exported content even
  when its originating plugin is inactive.
- Field-usage analysis can observe stale metadata and classify it as core when
  the inactive plugin's field definitions are unavailable.
- Some integrations are detected from stored options alone, so abandoned
  webhook, analytics, CRM, or newsletter options can remain visible.
- Inactive role-management plugins are deliberately recorded as installed but
  inactive.

This residual evidence is usually small, but blindly deleting it is unsafe.
Inactive ACF values, abandoned shortcode markup, stale block comments, or
plugin-owned rows can still drive visible public content.

## Product principles

1. Never activate or execute inactive plugin code during export.
2. Preserve objective source observations in the exporter; make target migration
   decisions in the harness.
3. Public reachability takes priority over plugin activation status.
4. Preserve referenced orphan data; compact unreferenced dormant data.
5. Never silently discard an unresolved public dependency.
6. Keep the first export bounded and support targeted secondary acquisition for
   large optional payloads.
7. Every retained, omitted, sampled, or deferred payload must have an explicit
   reason and evidence lineage.
8. Security filters and private-content exclusions apply before relevance or
   acquisition decisions.

## Responsibility boundary

| Component | Responsibility |
| --- | --- |
| `moltex_exporter` | Observe plugin status, likely ownership, public references, counts, hashes, bounded samples, and payload availability. |
| H1 intake | Validate the new artifact, enforce limits, verify checksums, and adapt older bundles. |
| H2 contracts | Derive migration relevance and dispositions from exporter facts with evidence lineage. |
| H3 conversion | Consume retained values, omit dormant evidence, and render explicit placeholders for unresolved public behavior. |
| H4 planning | Create bounded conversion/replacement tasks and block only unresolved public dependencies. |
| Generated verifier | Prove that referenced evidence was converted, deliberately deferred, or represented by an approved placeholder. |
| H6 harness/evals | Exercise active, inactive, removed, referenced, dormant, unknown, and mutation cases end to end. |

The exporter must not label evidence as required for Astro, decide replacement
behavior, or generate target code.

## New bundle artifact

Add a required, versioned `legacy_evidence_index.json` artifact for new bundle
versions. Older supported bundles receive a conservative compatibility adapter in
H1.

The index contains observations only. A representative entry is:

```json
{
  "evidence_id": "legacy:postmeta:page:hero_title",
  "artifact_type": "postmeta_field",
  "source_plugin": "advanced-custom-fields",
  "ownership_confidence": "high",
  "plugin_status": "inactive",
  "source_identity": {
    "post_type": "page",
    "field_name": "hero_title"
  },
  "relationship_status": "referenced",
  "public_reference_count": 12,
  "reference_evidence": [
    "content/page/home.json#/postmeta/hero_title"
  ],
  "payload": {
    "status": "included",
    "method": "bundle",
    "artifact": "legacy/postmeta/page/hero_title.json",
    "row_count": 12,
    "sha256": "..."
  },
  "source_lineage": [
    "wp_postmeta:post_type=page,meta_key=hero_title"
  ]
}
```

### Required entry fields

- `evidence_id`: stable source-derived identifier, never array-position based.
- `artifact_type`: `postmeta_field`, `custom_table`, `option`, `shortcode`,
  `block`, `custom_post_type`, `taxonomy`, `widget`, `integration`, or
  `media_reference`.
- `source_plugin`: normalized plugin family or `unknown`.
- `ownership_confidence`: `high`, `medium`, `low`, or `unknown`.
- `plugin_status`: `active`, `inactive`, `missing`, or `unknown`.
- `source_identity`: type-specific stable identity.
- `relationship_status`: `referenced`, `unreferenced`, or `unknown`.
- `public_reference_count`: non-negative integer.
- `reference_evidence`: bounded artifact paths and JSON pointers.
- `payload.status`: `included`, `sampled`, `deferred`, `unavailable`, or
  `omitted`.
- `payload.method`: `bundle`, `source-fetch`, `targeted-export`,
  `operator-decision`, or `none`.
- `payload.artifact`: bundle path only when a payload is included or sampled.
- `payload.row_count`, `payload.sha256`, and bounded size metadata when
  applicable.
- `source_lineage`: redacted source observations sufficient to audit ownership
  and reachability.

The bundle validator must enforce the same acquisition consistency already used
for media:

- `included` and `sampled` require a valid artifact and checksum.
- `deferred` requires no bundled artifact and declares an acquisition method.
- `unavailable` and `omitted` require no bundled artifact.
- Every artifact path must be registered, contained, checksummed, and unique.

## Plugin ownership signatures

Create a declarative, tested signature registry. A plugin family may declare:

- Installed plugin slugs and main files.
- PHP constants/classes/functions that prove active runtime registration.
- Table prefixes and exact table names.
- Option and postmeta prefixes.
- Shortcode names.
- Gutenberg block namespaces.
- CPT and taxonomy names.
- Widget bases and integration option names.

Signatures provide ownership evidence only. They must not load inactive PHP or
infer target behavior. Unknown evidence remains `unknown`; it is never assigned
to a plugin merely because of a weak substring collision.

## Exporter observation workflow

### 1. Build plugin status inventory

Combine installed plugins, `active_plugins`, network activation where supported,
and observed runtime registrations into a normalized inventory. Record active,
inactive, missing, and unknown separately.

### 2. Build the public-reference graph

Scan only export-eligible public content and active public configuration for:

- Shortcode tags in raw content.
- Gutenberg block namespaces and attributes.
- CPT and taxonomy relationships.
- Postmeta attached to exported content IDs.
- Media, route, post, term, user-safe, and object relationships in field values.
- Active widgets, menus, page templates, and reusable patterns.
- Table columns such as `post_id`, `object_id`, `item_id`, `entry_id`, and
  `form_id` that can be joined to exported public objects.
- Integration settings that are demonstrably referenced by active public output.

Draft, private, future, trashed, authentication-only, and sensitive data remain
subject to the existing export policy before graph construction.

### 3. Describe payload availability

For every discovered legacy artifact, record whether a bounded payload is already
included, can be obtained with a targeted export, can be fetched from a public
source, requires operator coordination, or is unavailable.

## Database-table retention policy

The first bundle records a compact manifest for every non-core table:

- Table name and likely owner.
- Plugin status and ownership confidence.
- Schema hash, bounded column/index description, and row count.
- Sensitive-table classification.
- Relationship columns and number of rows reachable from exported public
  objects.
- Payload status and acquisition method.

Payload rules:

| Observation | Initial payload |
| --- | --- |
| Active supported plugin and publicly required table | Export bounded required rows. |
| Inactive/missing plugin with rows reachable from public content | Export only reachable non-sensitive rows, or defer them when over limits. |
| Inactive/missing plugin with no public references | Manifest only; omit rows. |
| Unknown owner with public references | Bounded sample plus decision evidence, subject to security filters. |
| Unknown owner with no public references | Manifest only. |
| Sensitive table | Never export merely because it is reachable; apply the security policy and require an explicit safe acquisition path. |

Rows must be selected deterministically by stable primary key. Limits, truncation,
and excluded-row counts must be explicit; sampling may never be presented as a
complete payload.

## Postmeta retention policy

Postmeta requires more conservative handling because templates can render values
that do not appear in `post_content`.

For every field on an exported public record, observe:

- Field name, inferred type, cardinality, and likely owner.
- Number of exported records using it.
- Whether values contain media, route, content, term, or object relationships.
- Whether it matches a known content-bearing field definition.
- Whether it matches a cache, lock, generated asset, analytics, revision, or
  operational-only signature.
- Total byte size, bounded samples, and stable hashes after security filtering.

Payload rules:

- Preserve values for recognized content-bearing fields on exported public
  records, even when the plugin is inactive or missing.
- Preserve relationship-bearing values needed to connect content or media.
- Omit known cache, transient, lock, session, generated CSS, analytics, and
  operational metadata values; retain only a compact omission record when useful.
- For unknown fields, include bounded values when size permits and otherwise
  defer with hashes, counts, types, and references.
- Never treat an unknown inactive-plugin field as core merely because its plugin
  API is unavailable.

### Inactive ACF handling

Detect ACF storage without calling ACF APIs:

```text
hero_title  = "Welcome"
_hero_title = "field_abc123"
```

The underscored field-key pairing is ownership/type evidence. Inspect stored
`acf-field-group` and `acf-field` records directly through safe WordPress database
queries when the plugin is inactive. Preserve public field values and definitions
needed to interpret them. Apply the same approach through declarative signatures
for Pods, Meta Box, and Carbon Fields where reliable storage contracts exist.

## Inactive shortcodes and blocks

Raw public content must be parsed independently of active runtime registries.

- A shortcode present in public content is referenced evidence even when its
  callback is unavailable.
- A non-core Gutenberg block comment is referenced evidence even when its block
  type is not registered.
- Preserve shortcode attributes, enclosed content, block attributes, and source
  location after security filtering.
- Do not execute callbacks or dynamic render functions.
- H2 decides whether a deterministic conversion exists or a replacement decision
  is required.

## H2 derived classifications

H2 derives target-facing classifications from exporter observations:

| Classification | Derivation | Default disposition |
| --- | --- | --- |
| `required` | Active source behavior or data demonstrably affects public output. | Preserve and convert. |
| `referenced_orphan` | Inactive/missing source plugin with a public reference. | Preserve; create a decision only when deterministic conversion is unavailable. |
| `dormant` | Inactive/missing plugin with no public references. | Exclude from canonical site contracts; retain compact audit evidence. |
| `unknown` | Ownership or reachability cannot be established. | Preserve bounded evidence; block only when public behavior may be affected. |
| `deferred` | Required payload is identified but not in the first bundle. | Retain acquisition contract and block its consumer until acquired. |

Every derived classification must cite fields from
`legacy_evidence_index.json`. H2 must not promote dormant evidence into route,
asset, capability, or task contracts.

## H1 intake changes

- Add a strict schema and model for `legacy_evidence_index.json`.
- Register it in the accepted bundle format and checksum validation.
- Reject unsafe paths, duplicate IDs, invalid acquisition combinations, excessive
  counts, excessive samples, and broken references.
- Add limits for entries, relationship edges, per-entry samples, and total legacy
  payload bytes.
- Add a compatibility adapter for older bundles. The adapter conservatively marks
  existing plugin/table/postmeta evidence as `unknown`; it must not invent
  reachability or ownership.
- Preserve the original accepted artifact and emit adapter provenance in the
  intake receipt.

## H3 conversion changes

- Materialize retained content-bearing values into canonical content models.
- Rewrite retained media and route relationships through immutable H2 maps.
- Do not copy dormant inventories into the generated Astro repository.
- Render visible, accessible placeholders for referenced orphan shortcodes or
  blocks whose behavior is unresolved.
- Attach stable capability/decision IDs to placeholders so H4 can localize work.
- Never call WordPress, inactive plugin code, or external AI services at runtime.

## H4 planning changes

- Generate conversion or replacement tasks for `required` and
  `referenced_orphan` evidence only when work remains.
- Generate acquisition tasks for `deferred` evidence before consumer tasks.
- Do not create implementation tasks for `dormant` evidence.
- Scope tasks to generated source paths and protected contract evidence.
- Link blocking tasks to real decision IDs through evidence subjects, never to
  human-readable prompts.
- Production readiness remains blocked while a public referenced orphan is
  unresolved, but not merely because inactive plugins are installed.

## Two-stage acquisition

The initial ZIP remains the complete source contract for bounded public content
and immediately required evidence. Large optional payloads use a second stage:

1. The first export emits stable evidence IDs, counts, hashes, relationships, and
   acquisition descriptors.
2. H2 determines that a deferred payload is required.
3. A targeted exporter workflow accepts a bounded acquisition request containing
   evidence IDs from the original bundle.
4. The exporter produces a separately checksummed payload bundle tied to the
   original bundle ID and site identity.
5. H1 verifies both bundles and H2 resolves the deferred contracts without
   changing their stable identities.

The request must never accept arbitrary SQL, paths, option names, or table names.
It can reference only evidence IDs previously issued by the exporter. A future
media-only plugin may use the same acquisition model through `media_map.json`.

## Security and privacy

- Apply credential, token, session, user, payment, submission, and private-content
  filters before hashing, sampling, relationship analysis, or payload writing.
- Do not expose raw SQL, absolute server paths, salts, API keys, webhook secrets,
  private emails, form submissions, or authentication material.
- Treat serialized PHP, JSON, HTML, CSS, shortcode attributes, and block
  attributes as untrusted data.
- Never unserialize arbitrary objects or invoke callbacks from stored values.
- Bound recursion, nesting, string lengths, relationship edges, samples, and
  table scans.
- Table and field identifiers must be allowlisted from observed evidence and
  safely quoted by the exporter; targeted acquisition accepts no free-form
  identifiers.

## Implementation phases

### Phase 1 — Characterization and signatures

1. Add fixtures covering active, inactive, missing, and unknown plugin families.
2. Characterize current inventory, postmeta, custom-table, shortcode, block,
   options, and media behavior before changing it.
3. Introduce the declarative plugin-signature registry with collision tests.
4. Add source-observation models without changing packaging behavior.

### Phase 2 — Exporter legacy evidence index

1. Build the plugin-status inventory.
2. Build the bounded public-reference graph.
3. Emit `legacy_evidence_index.json` through the central validated writer.
4. Register the artifact, schema, checksums, byte limits, and bundle validation.
5. Keep raw plugin code, readmes, and templates omitted.
6. Add admin-export summary counts for required candidates, referenced orphans,
   dormant evidence, unknown evidence, included payloads, and deferred payloads.

### Phase 3 — Database and postmeta payload reduction

1. Replace blanket custom-table detail with manifest-first output.
2. Export only safe rows reachable from public objects for inactive/missing
   plugin tables.
3. Add postmeta ownership, operational-field exclusion, size accounting, and
   deferred payload rules.
4. Add inactive ACF/Pods/Meta Box/Carbon Fields storage recognition.
5. Record every omission, sample, truncation, and deferral explicitly.

### Phase 4 — H1 and H2 contract support

1. Add versioned intake and canonical models.
2. Add bundle adapters for previous supported exporter versions.
3. Verify evidence IDs, relationships, artifacts, checksums, and acquisition
   consistency.
4. Derive H2 classifications and dispositions with lineage.
5. Integrate referenced fields/rows with content, route, asset, media,
   capability, parity, and decision contracts.

### Phase 5 — H3 and H4 consumption

1. Materialize retained content fields and relationships.
2. Add unresolved shortcode/block placeholders.
3. Add deferred acquisition dependencies.
4. Exclude dormant evidence from generated repositories and task graphs.
5. Generate bounded replacement tasks and block only unresolved public behavior.

### Phase 6 — Verifier, evals, and documentation

1. Add verifier checks for referenced-evidence disposition and payload integrity.
2. Add mutations that drop a referenced orphan, include dormant bulk rows, forge
   a reference, change a payload checksum, or attach an artifact to an invalid
   acquisition state.
3. Add reproducibility tests for ordering, IDs, hashes, and classification.
4. Run a large inactive-plugin fixture and compare ZIP size and useful artifact
   parity with the current exporter.
5. Update `moltex.md`, `moltex_harness.md`, both project READMEs, bundle schemas,
   release notes, and operator troubleshooting guidance.

## Test matrix

| Scenario | Expected result |
| --- | --- |
| Active plugin, public block and data | Full required evidence and payload. |
| Inactive plugin, shortcode remains on a public page | Referenced orphan; shortcode preserved; no callback execution. |
| Removed ACF plugin, public ACF value and field-key pair remain | Value and definition evidence preserved and typed where possible. |
| Inactive plugin, large table with no public relationships | Manifest only; zero table rows in initial payload. |
| Inactive plugin, large table with three rows linked to public posts | Three safe rows included or deferred; all counts explicit. |
| Unknown table with no public relationships | Compact unknown manifest; no production blocker. |
| Unknown field affects public media relationship | Bounded evidence plus H2 decision/acquisition contract. |
| Stale API key or webhook secret | Redacted before any artifact, sample, or hash is exposed. |
| Older supported bundle without legacy index | Conservative H1 adapter succeeds and marks evidence unknown. |
| Invalid payload status/artifact combination | Intake rejects the bundle. |
| Referenced orphan removed by mutation | Verifier fails and localizes the missing evidence. |
| Dormant rows injected by mutation | Size/relevance verifier fails or flags unjustified payload. |

## Acceptance criteria

- Installing many inactive plugins without public references adds only bounded
  inventory and manifest evidence, not plugin code or bulk data.
- Inactive or removed plugin data that still affects public content is preserved
  with stable IDs and lineage.
- No inactive plugin PHP is loaded or executed.
- Dormant custom tables contribute no row payload to the initial ZIP.
- Referenced custom-table payload includes only safe reachable rows or a declared
  deferred acquisition contract.
- Recognized content-bearing postmeta survives plugin deactivation.
- Known operational/cache metadata values do not enter canonical content.
- H2, not the exporter, decides target relevance and replacement behavior.
- Dormant evidence does not create Astro files, capability contracts, decisions,
  or H4 implementation tasks.
- Every omitted, sampled, included, unavailable, or deferred payload is auditable.
- Older supported exports remain ingestible through explicit adapters.
- Clean, negative, mutation, reproducibility, and end-to-end tests pass.
- A representative inactive-plugin-heavy site produces a materially smaller ZIP
  without losing any artifact required to rebuild its public routes.

## Rollout

1. Land schemas and readers before enabling payload reduction.
2. Emit the legacy index alongside current artifacts for one compatibility
   release and compare classifications in tests.
3. Enable manifest-first custom-table handling behind a bundle-format/version
   gate, never a silent behavior change for the same format.
4. Enable postmeta reduction only after inactive-ACF and unknown-field fixtures
   demonstrate no public-content loss.
5. Add targeted acquisition after first-bundle contracts and stable evidence IDs
   are proven reproducible.
6. Remove superseded legacy artifacts only in a declared bundle-version change
   with adapters and release notes.

## Explicit non-goals

- Reconstructing or executing inactive plugin PHP.
- Migrating private users, sessions, payments, submissions, or credentials.
- Treating plugin activation as proof that all plugin data is required.
- Treating deactivation as proof that all plugin data is irrelevant.
- Allowing the exporter to choose Astro implementations.
- Allowing targeted acquisition to execute arbitrary SQL or retrieve arbitrary
  filesystem paths.
