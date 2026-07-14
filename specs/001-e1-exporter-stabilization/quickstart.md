# Quickstart: Validate E1

## Prerequisites

- PHP 8.2 with ZipArchive and the extensions required by WordPress
- Composer 2
- Docker Desktop with the Linux engine running

Install PHP test dependencies:

```powershell
composer install --working-dir moltex_exporter
```

## Local exporter checks

Run the exact Phase E1 command set from the repository root:

```powershell
php -l moltex_exporter/moltex_exporter.php
php moltex_exporter/tests/content_export_regression.php
php moltex_exporter/tests/sample_scope_regression.php
php moltex_exporter/tests/export_directory_regression.php
php moltex_exporter/tests/packager_download_regression.php
moltex_exporter/vendor/bin/phpunit moltex_exporter/tests
```

Expected outcome: every command runs in the documented environment. Passing commands,
failures, and any unavailable prerequisites are recorded separately in
`docs/verification/e1-verification-receipt.md`; only that receipt determines whether a
failure is repaired or explicitly classified under the E1 exit gate.

## Disposable WordPress smoke

```powershell
powershell -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-smoke.ps1
```

Expected outcome: the script installs WordPress and the plugin, performs complete and
discovery exports, downloads both ZIPs, and writes a count comparison and candidate
`legacy-1` fixture for review.

## Privacy and fixture acceptance

Review the candidate ZIP using the procedure in `docs/exporter-audit.md`. Only after the
review is clean, copy it to `samples/legacy-1-export.zip`, generate its SHA-256 sidecar, and
record both results in the separate verification receipt.
