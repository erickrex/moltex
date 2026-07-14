# Data Model: E1 Evidence

## Scanner Classification

- `registry_key`: unique scanner key from the executable registry
- `class` and `source_file`: implementing class and file
- `priority`: execution order
- `disposition`: required, optional evidence, diagnostic, or excluded
- `rationale`: reason for the disposition
- `consumer`: intended `moltex_harness` area or `none`

Validation: exactly 33 unique registry keys; every row has one disposition and a rationale.

## Artifact Classification

- `path_pattern`: literal or bounded dynamic ZIP-relative path
- `producer`: exporter/scanner method that emits it
- `version_behavior`: `legacy-1` current/unversioned behavior
- `privacy_class`: public, internal diagnostic, sensitive-filtered, or excluded
- `size_risk`: bounded, content-scaled, media-scaled, database-scaled, or unbounded risk
- `consumer`: intended harness area or `none`
- `conditions`: mode/plugin/theme/content conditions controlling emission

Validation: every identified write/copy path maps to one row; dynamic patterns state bounds.

## Verification Check

- `id`, `command`, `environment`, `timestamp`
- `status`: PASS, FAIL, BLOCKED, or NOT-RUN
- `exit_code`, `summary`, `evidence`, `remediation`

State transition: NOT-RUN → PASS/FAIL/BLOCKED; FAIL/BLOCKED → PASS only after a new recorded run.

## Smoke Export Comparison

- source fixture identity and WordPress/plugin versions
- complete and discovery artifact/content/media counts
- packaging and download results
- explained differences and unresolved mismatches

## Legacy Fixture

- ZIP-relative artifact inventory
- SHA-256 checksum
- generation command and source fixture
- privacy review status and findings
- compatibility label: `legacy-1`

Validation: checksum matches bytes; privacy findings have no unresolved sensitive item.
