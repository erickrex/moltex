# Moltex Exporter Verification

E1–E3 are cumulative. Documentation is not proof; acceptance requires the commands below
and the checked-in receipts.

## Prerequisites

- PHP 7.4 for the declared minimum and PHP 8.2 for the reference run
- Composer 2 with PHP ZipArchive
- Docker Desktop
- Google Chrome, Microsoft Edge, or an explicit Chromium `-BrowserPath`

Install locked development dependencies:

```powershell
composer install --working-dir moltex_exporter
```

## Cumulative local gate

```powershell
php moltex_exporter/vendor/phpunit/phpunit/phpunit -c moltex_exporter/phpunit.xml.dist
php moltex_exporter/tests/content_export_regression.php
php moltex_exporter/tests/sample_scope_regression.php
php moltex_exporter/tests/export_directory_regression.php
php moltex_exporter/tests/packager_download_regression.php
php moltex_exporter/tests/audit_inventory_regression.php
php moltex_exporter/tests/callback_path_regression.php
php moltex_exporter/tests/identity_regression.php
php moltex_exporter/tests/privacy_fixture_regression.php samples/golden-export.zip
php moltex_exporter/tools/validate-bundle.php samples/moltex-export-1.zip
php moltex_exporter/tools/validate-bundle.php samples/golden-export.zip
```

## Disposable WordPress gates

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-smoke.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-golden-path.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-release-smoke.ps1
```

The normal smoke proves complete/discovery behavior and signed downloads. The Golden Path
stages a candidate under ignored `golden-output/` and never overwrites the reviewed oracle.
The release smoke uploads and activates the exact development-free release ZIP in fresh
minimum and reference WordPress environments.

Chrome is auto-detected before Edge. `-BrowserPath C:\path\to\chromium.exe` selects a
specific installation. Candidate reports record browser name/version; the browser is
tooling, not part of `moltex-export/1`.

## Fixture policy

Tests never regenerate their own oracle. The synthetic contract sample changes only through
its explicit maintainer builder. The real Golden Export changes only through
[`docs/verification/e3-replacement-procedure.md`](../../docs/verification/e3-replacement-procedure.md)
after count, visual, capability, privacy, and validator review.

The old mock `IntegrationTest.php` and direct-browser scanner scripts were removed because
they did not prove live integration. Real integration belongs to the disposable WordPress
and install-from-release workflows.
