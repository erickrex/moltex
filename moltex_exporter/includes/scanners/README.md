# Exporter Scanner Architecture

Scanner classes observe one bounded aspect of the source WordPress site. They are loaded
and ordered by `Moltex_Exporter_Scanner`; scanner output is passed through the exporter and
the declarative artifact registry before packaging.

## Rules

- Scanners extend `Moltex_Exporter_Scanner_Base` and return structured arrays.
- The content scanner owns eligible-item enumeration, per-item records, bounded rendered
  HTML, and completeness counts.
- The media scanner copies only referenced public originals and explicitly reviewed
  screenshot attachments.
- Migration readiness owns static-site eligibility and known blockers; unknown behavior
  remains a manual-review item.
- Required JSON is written only by the central validated writer. Scanners must not create
  undocumented required artifacts.
- Errors and warnings use the shared classified logger. Optional missing evidence must not
  be reported as a successful required artifact.
- A new scanner requires a declared bundle consumer and behavior-focused coverage.

The registry/audit regression verifies the current scanner inventory. Run scanner coverage
through PHPUnit and the disposable WordPress workflows documented in
[`../../tests/README.md`](../../tests/README.md). There are no browser-accessible scanner
test scripts in a production installation.
