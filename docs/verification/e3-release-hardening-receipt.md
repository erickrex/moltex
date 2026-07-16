# E3 Release Hardening Verification Receipt

**Date:** 2026-07-17

**Release:** Moltex Exporter 1.2.0; bundle contract remains `moltex-export/1`

**Status:** ACCEPTED FOR STAGING PILOT

## Release artifact

- Release-content commit: `8495266c778a3861450fac537214612e22ee1c1b`
- File: `dist/moltex-exporter-1.2.0.zip`
- Size: 185,984 bytes; 71 files under the single `moltex-exporter/` directory
- SHA-256: `9ba40033a7ccf30b9e16805aadb0b2dfd3efd71f0b62ed1016497f1b9f3405a0`
- Build policy: clean Git tree, four matching version declarations, explicit runtime
  allowlist/requirements, and explicit development-file denials
- Archive review: no tests, fixtures, vendor, Composer/PHPUnit files, examples, build
  configuration, or repository-only scanner material

## Compatibility and install-from-ZIP matrix

The same release ZIP was uploaded through the normal WordPress plugin-upload endpoint,
activated, preflighted, exported, downloaded through its signed URL, and validated outside
the request lifecycle in each fresh environment.

| Environment | Result | Complete counts | Validator |
|---|---|---|---|
| WordPress 5.9.10 / PHP 7.4.29 | PASS | pages 3/3, posts 4/4, 379 artifacts | valid; complete eligible |
| WordPress 7.0.1 / PHP 8.2.32 | PASS | pages 3/3, posts 4/4, 396 artifacts | valid; complete eligible |
| WordPress 7.0.1 discovery | PASS | pages 1/3, posts 1/4, 387 artifacts | valid; correctly ineligible |

The minimum Apache image digest was
`wordpress@sha256:f9d68493ee98ea8f39e6e0fc2327b48e0b555ef0ec3fcc06b8d42cbc539c49a4`;
WordPress core was explicitly pinned to 5.9.10 before installation. The reference image
digest was
`wordpress@sha256:c94b9860250a8785025f8be9b9a38bc59bbe07e78e844a17becffa4de30b7087`.

## Verification summary

- PHPUnit: PASS — 111 tests, 1,668 assertions after Golden promotion
- PHP 7.4 syntax: PASS across production, test, template, fixture, and validator PHP
- Cumulative standalone regressions: PASS
- Synthetic and frozen Golden validators: PASS
- Normal complete/discovery WordPress smoke: PASS
- Release install smoke: PASS, including screenshot save through the protected admin action
- 1.2.0 Golden replacement: PASS — 8 content, 2 media, 2 reviewed screenshots,
  8 HTML snapshots, 8 SEO rows, 401 validated artifacts
- Privacy: PASS — private content disabled; all three canaries absent
- Screenshot review: PASS — Chrome 149 desktop 1440×1200 and mobile 500×844
- Disposable cleanup: PASS — both compatibility stacks and the Golden stack removed

## Disposition

The package is accepted for the staging-clone pilot described in
`e3-staging-pilot-runbook.md`. Production use still requires a validated complete export,
complete counts, expected visual evidence, no unresolved readiness blockers, and manual
privacy review. This receipt proves exporter release behavior; H1 is still required to
prove the exporter-to-harness rebuild handshake.
