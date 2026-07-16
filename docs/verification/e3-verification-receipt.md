# Phase E3 Verification Receipt

**Phase:** E3 — Freeze the Golden Path export

**Date:** 2026-07-16

**Contract:** `moltex-export/1`

**Status:** ACCEPTED

## Frozen evidence

- Real disposable WordPress export: `samples/golden-export.zip`
- Bundle ID: `sha256:1700381e5023e1ee456439f62ba00e17bd5af18917169c76679fd17fe5aba03f`
- ZIP SHA-256: `12929f58f44ce82d2f22de84bd05ce4bd24dc7a5d4160d4ff6e3fa0224253478`
- Standalone report: `samples/golden-export.validation.json`
- Reviewed expectations: `samples/golden-export.expected.json`
- Pinned versions: exporter `1.2.0`, manifest `1`, artifact schemas `1` / `1.0.0` as
  enumerated in the reviewed expectations; every schema file is checksummed in `bundle.json`

## Executable evidence

The final clean workflow created five public pages, three public posts, a hierarchical
navigation, two referenced original images with alternative text, resolved SEO for all
eight routes, a repeatable three-post family, an explicit YouTube capability, one private
post, and privacy canaries. It captured desktop and responsive mobile screenshots, exported
with private content disabled, downloaded through the signed endpoint, ran the standalone
validator, reconciled source/report/archive counts, and removed all disposable state.

| Check | Result |
|---|---|
| Standalone ZIP validation | PASS — 401 inventoried artifacts, no errors or warnings |
| Complete migration eligibility | PASS |
| Source/report/archive reconciliation | PASS — 8 content, 2 media, 2 screenshots, 8 snapshots, 8 SEO records |
| Scanner execution | PASS — 0 errors; 2 classified optional-file warnings |
| Privacy canaries | PASS — no private content or sensitive marker exported |
| Capability review | PASS — `embed:youtube` recorded once with explicit disposition |
| Visual review | PASS — Chrome 149 desktop and responsive mobile evidence accepted |
| PHPUnit | PASS — cumulative suite green after 1.2.0 promotion |
| PHP syntax and standalone regressions | PASS |
| Retained complete/discovery smoke | PASS — both ZIPs valid; eligibility classified correctly |
| Disposable cleanup | PASS — containers, network, and named volumes removed |

The two scanner warnings are the established clean-fixture absence of optional
`redirects_candidates.csv` and `schema_mysql.sql`; neither is required for this fixture's
complete-migration eligibility.

**E3 acceptance:** ACCEPTED. The Golden Export is a pinned, reviewed downstream contract
fixture and can only be replaced through the explicit procedure.
