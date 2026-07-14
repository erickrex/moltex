# Feature Specification: E1 Exporter Stabilization

**Feature Branch**: `master` (pilot in the existing workspace)

**Created**: 2026-07-14

**Status**: Implemented and accepted

**Input**: Phase E1, “Audit and stabilize the existing exporter,” from `moltex.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trust the Current Export Surface (Priority: P1)

As a migration developer, I can see which scanners run, which artifacts they emit, and
how each item is classified so later contract work starts from verified facts.

**Why this priority**: E2 cannot safely change a surface that has not been inventoried.

**Independent Test**: Review the scanner and artifact tables against the registry and
writer call sites; every registered scanner and emitted path has exactly one disposition.

**Acceptance Scenarios**:

1. **Given** the current exporter registry, **When** the audit is reviewed, **Then** all 33
   registered scanners are classified as required, optional evidence, diagnostic, or
   excluded with a reason.
2. **Given** current artifact producers, **When** the artifact table is reviewed, **Then**
   every emitted file records its producer, version behavior, privacy class, size risk,
   and intended `moltex_harness` consumer or explicit lack of consumer.

---

### User Story 2 - Reproduce Exporter Behavior (Priority: P2)

As a maintainer, I can run the exporter’s real checks and smoke exports in a documented
environment and distinguish executable evidence from documentation claims.

**Why this priority**: Stabilization requires reproducible behavior before contract changes.

**Independent Test**: From the documented environment, run the syntax check, four
standalone regressions, PHPUnit suite, and complete/discovery WordPress smoke exports; the
receipt records every command, result, and prerequisite.

**Acceptance Scenarios**:

1. **Given** the documented PHP/Composer environment, **When** the verification commands
   run, **Then** failures are fixed or explicitly classified and no claimed check is hidden.
2. **Given** a disposable WordPress installation, **When** complete and discovery exports
   run, **Then** the plugin installs, packages, and downloads both ZIPs and records a count
   comparison.

---

### User Story 3 - Freeze a Safe Moltex Baseline (Priority: P3)

As a downstream consumer owner, I receive a sanitized current-format compatibility ZIP and
Moltex-branded documentation without stale product identity or leaked private material.

**Why this priority**: The baseline is the compatibility input for later exporter and
harness phases.

**Independent Test**: Search exporter-facing files for stale names, review privacy filters,
inspect the sample ZIP, verify its checksum, and confirm the privacy record covers secrets,
PII, server paths, and private content.

**Acceptance Scenarios**:

1. **Given** exporter-facing code and documentation, **When** identity checks run, **Then**
   stale product names are absent from user-visible metadata, copy, examples, and test docs.
2. **Given** the frozen `legacy-1` sample, **When** privacy and checksum checks run, **Then**
   the sample contains no known sensitive material and its recorded checksum matches.

### Edge Cases

- A scanner is registered conditionally or produces multiple dynamically named artifacts.
- An artifact has no planned harness consumer or is too sensitive or unbounded to retain.
- PHP, Composer, PHPUnit, or the disposable WordPress fixture is unavailable.
- Complete and discovery exports disagree for a reason not explained by mode semantics.
- A sample contains credentials, email addresses, private posts, or absolute server paths.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The audit MUST inventory and classify all 33 registered scanners.
- **FR-002**: The audit MUST map every emitted file to its producer, schema/version behavior,
  privacy classification, size risk, and intended harness consumer.
- **FR-003**: The project MUST document a reproducible PHP/Composer test environment and
  exact verification commands.
- **FR-004**: The verification MUST run the available syntax, standalone regression, and
  PHPUnit checks and explicitly record unavailable or failed checks.
- **FR-005**: A disposable WordPress site MUST demonstrate install, complete export,
  discovery export, packaging, and ZIP download.
- **FR-006**: Exporter-facing metadata, admin copy, README content, examples, and test
  documentation MUST use the Moltex identity without unnecessary behavioral changes.
- **FR-007**: Sensitive option/meta filters and a sample export MUST be reviewed for secrets,
  PII, absolute server paths, and private content.
- **FR-008**: A sanitized current-format ZIP MUST be frozen as
  `samples/legacy-1-export.zip` with a recorded checksum.
- **FR-009**: Required evidence MUST include `docs/exporter-audit.md`, scanner and artifact
  classification tables, command/test results, complete-versus-discovery counts, and a
  privacy review record.
- **FR-010**: The real E1 verification receipt MUST be stored separately from this Spec Kit
  specification and task plan.

### Key Entities

- **Scanner classification**: Registered scanner, disposition, rationale, and consumer.
- **Artifact classification**: Emitted path, producer, version behavior, privacy class,
  size risk, and consumer.
- **Verification receipt**: Environment, command, timestamp, result, evidence, and blocker.
- **Legacy fixture**: Sanitized current-format ZIP, checksum, provenance, and review status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 33 of 33 registered scanners and 100% of identified emitted files have a
  reviewed classification with no unexplained entry.
- **SC-002**: 100% of the six declared local verification commands have a recorded pass,
  failure classification, or explicit missing-prerequisite status.
- **SC-003**: One complete and one discovery export install/package/download path is proven
  on a disposable WordPress site and their content counts are reconciled.
- **SC-004**: Zero stale product-name matches remain in user-facing exporter files.
- **SC-005**: The frozen fixture passes its checksum and manual privacy review with zero
  unresolved credential, PII, private-content, or absolute-path findings.

## Dependencies and Scope

- Depends on the existing `moltex_exporter` registry, scanners, writers, regressions, and
  WordPress mocks being treated as the current behavior to stabilize.
- Depends on an executable PHP/Composer/PHPUnit environment and a disposable WordPress site
  to satisfy the exit gate; absence blocks acceptance rather than becoming a silent skip.
- `moltex_harness` is referenced only as the intended artifact consumer. No harness runtime,
  Astro generation, E2 bundle contract, new schema, or target migration decision is in scope.

## Deliverables and Exit Gate

Deliverables are `docs/exporter-audit.md`, complete scanner and artifact tables, captured
commands/results, `samples/legacy-1-export.zip` plus checksum, complete-versus-discovery
counts, a privacy review, corrected Moltex-facing copy, and a separate E1 verification
receipt.

E1 exits only when all required tests run in a documented environment; known failures are
fixed or classified; a disposable WordPress site installs, exports, packages, and downloads
a ZIP; stale product names are absent from user-facing exporter files; and the current
artifact surface is documented before contract changes begin.

## Assumptions

- The current unversioned ZIP is named `legacy-1` for compatibility; E1 does not redesign it.
- Documentation-only identity corrections should not alter export behavior.
- Real-site evidence must be sanitized before it is committed.
