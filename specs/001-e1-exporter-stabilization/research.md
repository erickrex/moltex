# Research: E1 Exporter Stabilization

## Decision: PHP and Composer baseline

- **Decision**: Verify with PHP 8.2.31, Composer 2, and PHPUnit 9.6 while retaining the
  plugin's declared PHP 7.4 minimum.
- **Rationale**: PHP 8.2 is currently installable from the Windows package source, PHPUnit
  9.6 supports PHP 7.4 through 8.2, and a committed Composer lock makes the test dependency
  repeatable without raising the production minimum.
- **Alternatives considered**: PHP 8.3+ would not validate the oldest supported range and
  increases deprecation noise; a container-only CLI would not exercise the exact E1 commands.

## Decision: Disposable WordPress smoke environment

- **Decision**: Add a Docker Compose WordPress 7.0.1/MariaDB 10.11.8 fixture plus a scripted
  smoke workflow that installs the plugin and runs complete and discovery exports.
- **Rationale**: It is disposable, reviewable, repeatable, and can prove packaging/download
  behavior without depending on a developer's live site. WordPress 7.0.1 is the current
  maintenance release at the time of the E1 pilot.
- **Alternatives considered**: A shared local WordPress install is not disposable; mocks
  cannot prove installation and HTTP download behavior.

## Decision: Inventory from executable registration and writes

- **Decision**: Derive scanner rows from `get_scanner_registry()` and artifact rows from
  exporter/scanner write and copy sites, then review conditional/dynamic paths manually.
- **Rationale**: Executable source is stronger evidence than README claims and exposes
  duplicate or conditionally emitted artifacts.
- **Alternatives considered**: Documentation-only inventory can drift; sample-only inventory
  misses conditional artifacts.

## Decision: Legacy fixture provenance

- **Decision**: Freeze only the sanitized output of the disposable smoke fixture and record
  its generation inputs, privacy review, and SHA-256 checksum.
- **Rationale**: A synthetic/disposable source avoids committing private production material
  and gives later phases a stable compatibility case.
- **Alternatives considered**: A production-site sample has unacceptable privacy risk;
  manufacturing an oracle directly from parsing code would make the fixture self-fulfilling.

## Decision: Verification status model

- **Decision**: Record each check as PASS, FAIL, BLOCKED, or NOT-RUN with command, environment,
  timestamp, evidence, and remediation. Only PASS satisfies an exit-gate item.
- **Rationale**: This prevents missing PHP, Composer, WordPress, or Docker prerequisites from
  being mistaken for success.
- **Alternatives considered**: Binary pass/fail cannot distinguish product failure from an
  unavailable prerequisite; prose-only receipts are hard to audit uniformly.
