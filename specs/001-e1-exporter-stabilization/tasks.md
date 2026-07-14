# Tasks: E1 Exporter Stabilization

**Input**: Design documents from `specs/001-e1-exporter-stabilization/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/evidence.md`

**Tests**: E1 explicitly requires syntax, standalone regression, PHPUnit, WordPress smoke,
identity, checksum, and privacy evidence. Regression tests precede behavior fixes.

**Organization**: Tasks are grouped by independently testable user story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the pinned E1 workflow and executable test dependency surface.

- [x] T001 Create the PASS/FAIL/BLOCKED/NOT-RUN receipt structure in `docs/verification/e1-verification-receipt.md`
- [x] T002 Add the PHP test dependency definition in `moltex_exporter/composer.json`
- [x] T003 Generate the dependency lock in `moltex_exporter/composer.lock`
- [x] T004 [P] Configure the PHPUnit suite in `moltex_exporter/phpunit.xml.dist`
- [x] T005 [P] Document PHP, Composer, PHPUnit, and smoke commands in `moltex_exporter/tests/README.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create uniform evidence and disposable smoke infrastructure used by all stories.

- [x] T006 Record uv 0.11.28, Spec Kit 0.12.15, and available environment prerequisites in `docs/verification/e1-verification-receipt.md`
- [x] T007 [P] Define pinned WordPress and database services in `moltex_exporter/tests/wordpress/docker-compose.yml`
- [x] T008 [P] Add deterministic public/private fixture content setup in `moltex_exporter/tests/wordpress/setup-fixture.sh`
- [x] T009 Implement complete/discovery export and ZIP-download orchestration in `moltex_exporter/tests/wordpress/run-smoke.ps1`
- [x] T010 Verify PHP/Composer/vendor and smoke artifacts are excluded in `.gitignore`

**Checkpoint**: Evidence schema and test environments are ready.

---

## Phase 3: User Story 1 - Trust the Current Export Surface (Priority: P1) MVP

**Goal**: Prove the registered scanner and emitted artifact surface before contract changes.

**Independent Test**: Registry and write-site review accounts for 33 scanner keys and every
identified literal or bounded dynamic emitted path.

### Tests for User Story 1

- [x] T011 [US1] Add a failing inventory-completeness regression in `moltex_exporter/tests/audit_inventory_regression.php`

### Implementation for User Story 1

- [x] T012 [US1] Document all 33 scanner classifications in `docs/exporter-audit.md`
- [x] T013 [US1] Document every identified artifact producer, version behavior, privacy class, size risk, condition, and consumer in `docs/exporter-audit.md`
- [x] T014 [US1] Run `moltex_exporter/tests/audit_inventory_regression.php` and record the passing evidence in `docs/verification/e1-verification-receipt.md`

**Checkpoint**: FR-001, FR-002, SC-001 are independently reviewable.

---

## Phase 4: User Story 2 - Reproduce Exporter Behavior (Priority: P2)

**Goal**: Execute the real local suite and complete/discovery WordPress smoke workflow.

**Independent Test**: All six declared commands and every smoke step have an accurate
receipt status; complete/discovery ZIP counts are reconciled.

### Tests for User Story 2

- [x] T015 [US2] Run the six-command E1 baseline and capture failures in `docs/verification/e1-verification-receipt.md`
- [x] T016 [US2] Add a focused failing regression under `moltex_exporter/tests/` for each product failure reproduced by T015

### Implementation for User Story 2

- [x] T017 [US2] Repair only failures reproduced by T015/T016 in the implicated file under `moltex_exporter/includes/`
- [x] T018 [US2] Re-run the six-command E1 suite and update `docs/verification/e1-verification-receipt.md`
- [x] T019 [US2] Run the disposable WordPress smoke workflow and retain sanitized outputs under `moltex_exporter/tests/wordpress/output/`
- [x] T020 [US2] Record complete-versus-discovery counts, install, packaging, and download evidence in `docs/exporter-audit.md`

**Checkpoint**: FR-003 through FR-005 and SC-002/SC-003 are independently verifiable.

---

## Phase 5: User Story 3 - Freeze a Safe Moltex Baseline (Priority: P3)

**Goal**: Remove stale identity and freeze a privacy-reviewed legacy compatibility fixture.

**Independent Test**: Identity search has zero user-facing stale matches; privacy review is
clean; the frozen ZIP checksum matches its sidecar.

### Tests for User Story 3

- [x] T021 [P] [US3] Add stale-identity assertions in `moltex_exporter/tests/identity_regression.php`
- [x] T022 [P] [US3] Add sensitive option/meta filter assertions in `moltex_exporter/tests/SecurityFiltersTest.php`

### Implementation for User Story 3

- [x] T023 [US3] Correct plugin metadata and user-facing identity in `moltex_exporter/moltex_exporter.php`
- [x] T024 [US3] Correct admin/readiness copy and hooks/examples in `moltex_exporter/templates/admin-page.php`, `moltex_exporter/includes/class-admin-page.php`, `moltex_exporter/includes/scanners/class-migration-readiness-scanner.php`, and `moltex_exporter/README.md`
- [x] T025 [US3] Correct executable coverage claims and Moltex naming in `moltex_exporter/tests/README.md`
- [x] T026 [US3] Harden verified sensitive option/meta exclusions in `moltex_exporter/includes/class-security-filters.php`
- [x] T027 [US3] Review the smoke ZIP for secrets, PII, private content, and absolute paths and record findings in `docs/exporter-audit.md`
- [x] T028 [US3] Freeze the reviewed ZIP and SHA-256 sidecar at `samples/legacy-1-export.zip` and `samples/legacy-1-export.zip.sha256`
- [x] T029 [US3] Run identity, security-filter, and checksum regressions and record results in `docs/verification/e1-verification-receipt.md`

**Checkpoint**: FR-006 through FR-009 and SC-004/SC-005 are independently verifiable.

---

## Phase 6: Polish and Exit-Gate Review

**Purpose**: Close the pilot with an accurate, separate real-world receipt.

- [x] T030 Re-run the quickstart sequence from `specs/001-e1-exporter-stabilization/quickstart.md`
- [x] T031 Reconcile every requirement and exit-gate item in `docs/verification/e1-verification-receipt.md`
- [x] T032 Mark E1 accepted only if every exit-gate row is PASS in `docs/verification/e1-verification-receipt.md`
- [x] T033 Review and mark completed task checkboxes in `specs/001-e1-exporter-stabilization/tasks.md`

---

## Dependencies and Execution Order

### Phase Dependencies

- Setup has no dependency.
- Foundational depends on Setup and blocks all user stories.
- US1, US2, and US3 depend on Foundational; execute in priority order for this pilot.
- Fixture freezing in US3 depends on a successful US2 complete export.
- Exit-gate review depends on all three stories.

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational; provides the audit baseline.
- **US2 (P2)**: Independent after Foundational; provides executable and smoke evidence.
- **US3 (P3)**: Identity work is independent, but the frozen fixture depends on US2 output.

### Within Each User Story

- Run or add the stated regression before changing behavior.
- Keep documentation sourced from executable registration/write sites and real command output.
- Do not mark blocked infrastructure as passing.

### Parallel Opportunities

- T004 and T005 touch different files after Composer metadata exists.
- T007 and T008 define separate smoke components before T009 integrates them.
- T021 and T022 are independent regressions.
- Scanner and artifact source review may be gathered concurrently, but both land sequentially
  in `docs/exporter-audit.md`.

## Parallel Example: User Story 3

```text
Task: T021 add stale-identity assertions in moltex_exporter/tests/identity_regression.php
Task: T022 extend sensitive-filter assertions in moltex_exporter/tests/SecurityFiltersTest.php
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational.
2. Complete US1 and validate the 33-scanner/artifact inventory.
3. Review the audit before making stabilization changes.

### Incremental Delivery

1. Audit surface (US1).
2. Establish executable behavior and smoke evidence (US2).
3. Correct identity/privacy and freeze the fixture (US3).
4. Re-run everything and issue the separate receipt.

## Format Validation

All 33 tasks use checkbox, sequential task ID, optional `[P]`, required story label for story
phases, an actionable description, and an explicit repository path.
