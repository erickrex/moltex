# E1 Evidence Contract

E1 evidence is reviewable Markdown plus a sanitized ZIP. This contract describes the
required fields without creating the E2 exporter bundle contract.

## Exporter audit

`docs/exporter-audit.md` MUST contain:

1. environment and executable coverage summary;
2. exactly 33 scanner classification rows;
3. an artifact classification row for every identified emitted path pattern;
4. complete-versus-discovery count comparison;
5. privacy review method, findings, and disposition;
6. known failures and blockers.

## Verification receipt

`docs/verification/e1-verification-receipt.md` MUST be separate from the spec and tasks. It
MUST identify the repository revision/worktree state, OS, PHP, Composer, PHPUnit, WordPress,
database, and Docker versions. Every prescribed command and smoke step MUST have a status,
timestamp, exit code when available, concise result, evidence link, and remediation.

Allowed statuses are `PASS`, `FAIL`, `BLOCKED`, and `NOT-RUN`. A missing prerequisite is
`BLOCKED`, never `PASS`. E1 acceptance requires all exit-gate rows to be `PASS`.

## Legacy fixture

`samples/legacy-1-export.zip` MUST be generated from the disposable E1 WordPress fixture,
sanitized before commit, and accompanied by `samples/legacy-1-export.zip.sha256`. The privacy
review MUST cover credentials, tokens, email addresses/PII, private content, database/server
paths, and source-site secrets. The ZIP MUST NOT claim the E2 `moltex-export/1` contract.
