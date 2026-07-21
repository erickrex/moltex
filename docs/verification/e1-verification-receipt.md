# Phase E1 Verification Receipt

**Phase**: E1 — Audit and stabilize the existing exporter
**Date opened**: 2026-07-14
**Repository**: `digital-lobster`
**Status**: ACCEPTED

## Status vocabulary

- **PASS**: the recorded command or gate completed successfully.
- **FAIL**: the product or test failed in an executable environment.
- **BLOCKED**: a required prerequisite or external fixture was unavailable.
- **NOT-RUN**: the check has not yet been attempted.

Only PASS satisfies an E1 exit-gate item.

## Environment

| Component | Status | Recorded value | Evidence / notes |
|---|---|---|---|
| Operating system | PASS | Windows 10 Education, x64 | Local development host |
| Git | PASS | 2.30.1.windows.1 | `git --version` |
| uv | PASS | 0.11.28 | Official Astral Windows installer; `uv --version` |
| GitHub Spec Kit (historical evaluation only) | PASS | 0.12.15, tag commit `7b91c1e` | Briefly tested during E1, but it slowed development and was dropped. It is not part of the current toolchain or required to reproduce the verification results. |
| PHP | PASS | 8.2.31 ZTS, VS16 x64 | Official PHP Windows archive SHA-256 `b0c2883017316528cc927f49fd31750baab3b52523c301644454c2f89c4b3de1` |
| PHP extensions | PASS | curl, fileinfo, intl, mbstring, mysqli, openssl, PDO MySQL, zip | `php -m` |
| Composer | PASS | 2.10.2 | Official PHAR SHA-256 `5ee7125f8a30a34d246cefdc0bc85b8a783b28f2aec968994118512350d28027` |
| PHPUnit | PASS | 9.6.35 installed from `composer.lock` | `moltex_exporter/vendor/bin/phpunit --version` |
| Docker Desktop | PASS | Client 26.1.4, Linux engine | `docker version`; disposable services removed after run |
| WordPress | PASS | 7.0.1 / PHP 8.2 | Authenticated disposable smoke environment |
| MariaDB | PASS | 10.11.8 | Disposable smoke environment |

### Installation note

Winget located PHP 8.2.31 but its manifest URL returned HTTP 404. The same version was
installed from PHP's official Windows release archive and its downloaded bytes were hashed
before extraction. The VC++ 2015–2022 x64 runtime is installed as `v14.51.36247.00`.

## Declared local verification commands

| ID | Command | Status | Exit | Result |
|---|---|---|---:|---|
| E1-C01 | `php -l moltex_exporter/moltex_exporter.php` | PASS | 0 | No syntax errors detected before stabilization edits |
| E1-C02 | `php moltex_exporter/tests/content_export_regression.php` | PASS | 0 | Baseline completed without assertion failure |
| E1-C03 | `php moltex_exporter/tests/sample_scope_regression.php` | PASS | 0 | `sample_scope_regression: ok` |
| E1-C04 | `php moltex_exporter/tests/export_directory_regression.php` | PASS | 0 | `export_directory_regression: ok` |
| E1-C05 | `php moltex_exporter/tests/packager_download_regression.php` | PASS | 0 | Baseline completed without assertion failure |
| E1-C06 | `moltex_exporter/vendor/bin/phpunit moltex_exporter/tests` | PASS | 0 | 68 tests, 244 assertions, 0 errors, 0 failures, 0 risky tests |

### PHPUnit repair history

The first executable run exposed 47 mock/bootstrap errors, five stale fixture failures, and
nine risky conditional tests. E1 then updated the WordPress mocks, scanner dependency setup,
isolated export directories, and media/taxonomy fixtures. The misleading mock-based
`IntegrationTest.php` was deleted because the disposable WordPress workflow is the real
integration test. Tightened media coverage reproduced and fixed a CDN media-map reset bug.
The final PHPUnit command is green; the WordPress 7.0.1 smoke separately exercises plugin
installation, scanners, exporter, packager, authenticated AJAX, and signed downloads.

## Additional E1 checks

| ID | Check | Status | Evidence / blocker |
|---|---|---|---|
| E1-A01 | 33-scanner and artifact inventory regression | PASS | 33 registry rows and 23 core literal artifacts checked; dynamic patterns reviewed in `docs/exporter-audit.md` |
| E1-I01 | Stale user-facing identity regression | PASS | Zero Strapi, Digital Ocean, or ChatGPT Sites matches in reviewed user-facing exporter files |
| E1-P01 | Sensitive option/meta regression | PASS | 3 tests, 10 assertions; nested and unprefixed PII cases included |
| E1-W01 | WordPress plugin install and activation | PASS | WordPress 7.0.1 fixture installed; plugin activated |
| E1-W02 | Complete export, package, signed download | PASS | 3,530,003-byte ZIP; 394 entries; 0 scanner errors |
| E1-W03 | Discovery export, package, signed download | PASS | 3,508,653-byte ZIP; 384 entries; 0 scanner errors |
| E1-W04 | Complete/discovery count reconciliation | PASS | 7 vs 2 content JSON and 7 vs 2 snapshots, explained by configured discovery limits |
| E1-F01 | `legacy-1` privacy review | PASS | 0 private/secret/admin-email/server-root hits; documented core example emails only |
| E1-F02 | `legacy-1` SHA-256 verification | PASS | `ced0450dc69cfb0adf537b32fda84ca02ef3e1f0467947b4a1c5ddbfc1e10dd4` |

Both exports reported two classified warnings: the clean fixture produced neither
`redirects_candidates.csv` nor `schema_mysql.sql`. The legacy exporter records those absent
optional side files as warnings; no scanner error occurred.

## Exit gate

| Gate | Status | Evidence |
|---|---|---|
| All required tests ran in a documented environment | PASS | All six declared commands pass |
| Known failures fixed or explicitly classified | PASS | Privacy/path leaks, stale PHPUnit fixtures, and CDN media mapping fixed |
| Plugin installs, exports, packages, and downloads on disposable WordPress | PASS | Complete and discovery authenticated smoke receipts above |
| Stale product names absent from user-facing exporter files | PASS | `identity_regression: ok` |
| Current artifact surface documented before E2 | PASS | `docs/exporter-audit.md`; `audit_inventory_regression: ok` |

**E1 acceptance**: ACCEPTED on 2026-07-14. The full PHPUnit suite, focused regressions, and
real WordPress smoke evidence are green.
