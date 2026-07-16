# Phase E3 Count Reconciliation

**Date:** 2026-07-16

**Fixture:** Lakeside Commons, disposable WordPress 7.0.1 / PHP 8.2 / MariaDB 10.11.8

**Bundle ID:** `sha256:a35d08da99edff0491a531ff55202bf3cf246aa25a661ad0e3b02a6338fea98a`

**ZIP SHA-256:** `430e581f40cff6560b98970d19d4cd92a7a328dd607f94c2a3fe49385d2eefdd`

The fixture was created on a fresh named volume, exported in complete mode with private
content disabled, downloaded through the signed endpoint, and validated outside the
WordPress request lifecycle. The workflow removed the containers, network, and volumes.

| Evidence family | WordPress source | Export report | ZIP inventory | Result |
|---|---:|---:|---:|---|
| Published pages | 5 | 5 exported, 0 failed | 5 content JSON | exact |
| Published posts | 3 | 3 exported, 0 failed | 3 content JSON | exact |
| Public content total | 8 | 8 exported | 8 JSON + 8 bounded HTML snapshots | exact |
| Referenced original media | 2 | 2 mapped | 2 files + 2 map rows | exact |
| Reviewed screenshots | 2 attachments | 2 manifest rows | 2 PNG files | exact |
| Resolved SEO pages | 8 public items | 8 page records | 8 page records | exact |
| Capability dispositions | 1 discovered | 1 integration row | `embed:youtube` once | exact |

Every public source ID is unique in the archive: posts `101`, `102`, `103`; pages `201`
through `205`. The navigation has eight items and nests the three repeatable posts beneath
Stories. The media map references each of the two original PNG artifacts once, with
non-empty alternative text.

Signed-off-by: Codex (E3 implementation review), 2026-07-16

Attested archive: `430e581f40cff6560b98970d19d4cd92a7a328dd607f94c2a3fe49385d2eefdd`
