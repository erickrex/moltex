# Moltex Export Bundle Contract

`moltex-export/1` is the default physical handoff emitted by `moltex_exporter` as of
plugin version 1.1.0. Legacy fixtures remain accepted inputs for the future harness, but
the exporter no longer packages an undocumented layout.

## Required artifacts

Every bundle contains these producer artifacts plus the checked-in schemas under
`schemas/`:

- `bundle.json`
- `site_blueprint.json`
- `site_settings.json`
- `menus.json`
- `export_completeness.json`
- `media/media_map.json`
- `migration_readiness.json`
- `seo_full.json`
- `forms_config.json`
- `integration_manifest.json`
- every emitted `content/{post_type}/{stable-name}.json` record

Optional JSON, CSV, HTML, binary, theme, plugin, asset, snapshot, and media evidence is
still listed and checksummed. The artifact registry in
`includes/class-artifact-registry.php` declares its producer, kind, required status,
schema, privacy class, and byte limit. The global limits are 5,000 files and 250 MiB of
uncompressed data; individual definitions impose smaller bounds.

## Manifest identity

`bundle.json` records the contract and exporter versions, creation timestamp, mode, site
origin, completeness, privacy policy, reconciled post-type counts, sorted artifact
inventory, artifact registry, and `bundle_id` formatted as `sha256:<hex>`.

The bundle ID hashes the canonical manifest with `bundle_id` and `created_at` omitted.
Two exports of unchanged fixture evidence therefore have the same normalized identity even
when their creation timestamps differ.

## Write and packaging rules

Required JSON uses the central validated writer. It normalizes relative POSIX paths,
rejects traversal and duplicate normalized paths, canonicalizes object keys, validates
before writing, applies byte limits, writes through a temporary file, and reports producer
and path context on failure.

Packaging requires `bundle.json`, builds the ZIP, then runs the standalone validator before
making the archive downloadable. The validator reads ZIP entries without extraction and
rejects unsafe or duplicate paths, symlinks, oversized input, missing or unlisted files,
checksum and byte mismatches, schema errors, identity mismatches, and contradictory counts,
complete declarations, or privacy declarations.

Run it from the repository root:

```powershell
php moltex_exporter/tools/validate-bundle.php samples/moltex-export-1.zip
```

Exit code 0 means the evidence is structurally valid. A discovery bundle may be valid while
`complete_migration_eligible` remains false. Exit code 1 is an invalid bundle; exit code 2
means the validator itself could not run, such as missing arguments or ZipArchive.

## Compatibility and fixtures

`samples/moltex-export-1.zip` is a reviewed synthetic E2 contract fixture with its expected
ID in `samples/moltex-export-1.bundle-id.txt`. It proves the exporter boundary, not the real
Golden Path. E3 owns freezing the sanitized real WordPress Golden Path ZIP.

Additive optional artifacts are compatible within version 1. Removing required fields or
changing their meaning requires a new major contract and a new harness adapter.
