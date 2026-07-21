# X7 Release and Support Readiness Receipt

**Date:** July 21, 2026  
**Implementation commit:** `d9ddc098c3559e164efdd925d97e4cf85ec7defa`  
**Status:** ACCEPTED LOCALLY; FRESH SUPPORTED STAGING PILOT REQUIRED

## Exact exporter artifact

- ZIP: `dist/moltex-exporter-1.2.10.zip`
- SHA-256: `7edc933d4c7c3017f1b4a7a5e1b6c583f020ba25954c28ec46d7036d4819f212`
- Bytes: 193,607
- Runtime files: 73
- Reproducibility: PASS; two clean builds were byte-identical
- Development-file audit: PASS; no tests, vendor tree, PHPUnit files, or Composer manifests

## WordPress release smoke

The exact ZIP was uploaded through WordPress, activated, used to produce signed downloads,
and validated outside the exporter in both matrix cases.

| Case | Runtime | Complete export | Discovery export |
|---|---|---|---|
| Minimum | WordPress 5.9.10, PHP 7.4.29 | PASS; 56 artifacts; bundle `sha256:e4e7afae49f17326bb9054bf8d191fd5ffe8a8725b6a9aa42e9e3db684a9b84a` | Not run |
| Reference | WordPress 7.0.1, PHP 8.2.32 | PASS; 56 artifacts; bundle `sha256:8bd242e9727e165371446afc00b613f36cef32a76dacfbca2372d70d341a1c9a` | PASS; correctly ineligible; bundle `sha256:1cb3d4e7ca20c4a91fee085ef16c501f03505caba16bb4e30b1e9402a9d39e97` |

## Harness and verifier evidence

- Harness: 176 tests passed; Ruff and mypy passed.
- Exporter: 151 tests/1,959 assertions passed; all standalone regressions and both accepted
  bundle validators passed.
- Golden clean eval: run `20260721-e1582aac2fc4`; locked install, Astro build, and
  baseline/migration/parity suites passed with cleanup.
- Golden mutation eval: run `20260721-227e98188211`; 14/14 defects detected, localized, and
  specifically attributed; cleanup rate 100%; semantic retries zero.

## Support boundary evidence

- Elementor and Divi active-plugin, post-meta, shortcode, and rendered-markup signals are
  explicit unsupported-page-builder evidence.
- Meganoche export
  `ef4cfeb7c421a72718be9d81a3de3ae96bb4689f6d8ab362313dbbd581bec7b3` was accepted by H1
  and compiled by H2, then stopped with exit 6/`static_ineligible` because Elementor data
  was present on four routes. No browser capture or Astro publication was attempted.

## Remaining external gate

The release still needs the checked-in staging pilot against a fresh real **supported**
content-led WordPress site, including manual privacy review of its downloaded bundle.
Meganoche cannot satisfy that gate because it is now correctly classified as an unsupported
Elementor site. No production-readiness claim is made until that supported staging receipt
exists.
