# Moltex Exporter Tests

This directory contains three distinct evidence layers. Do not treat documentation as proof
that a scenario executes.

## Prerequisites

- PHP 8.2 for the E1 reference run (the plugin still declares PHP 7.4+)
- Composer 2 and PHP ZipArchive
- Docker Desktop for the disposable WordPress smoke fixture

Install the locked development dependencies from the repository root:

```powershell
composer install --working-dir moltex_exporter
```

## Required E1 commands

Run these exact commands from the repository root:

```powershell
php -l moltex_exporter/moltex_exporter.php
php moltex_exporter/tests/content_export_regression.php
php moltex_exporter/tests/sample_scope_regression.php
php moltex_exporter/tests/export_directory_regression.php
php moltex_exporter/tests/packager_download_regression.php
moltex_exporter/vendor/bin/phpunit moltex_exporter/tests
```

The root `phpunit.xml.dist` loads the WordPress mocks for the prescribed final command. The
project-local equivalent is:

```powershell
php moltex_exporter/vendor/phpunit/phpunit/phpunit -c moltex_exporter/phpunit.xml.dist
```

## Required E2 commands

E2 retains the E1 suite and adds contract validation:

```powershell
php moltex_exporter/vendor/phpunit/phpunit/phpunit -c moltex_exporter/phpunit.xml.dist
php moltex_exporter/tests/content_export_regression.php
php moltex_exporter/tools/validate-bundle.php samples/moltex-export-1.zip
powershell -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-smoke.ps1
```

The smoke runs the standalone validator against both downloaded ZIPs. A clean complete
bundle is complete-migration eligible; discovery remains valid evidence but is not eligible.
The synthetic sample is regenerated only by the explicit maintainer script
`tests/build-contract-sample.php`; tests never regenerate their expected fixture.

## Standalone regressions

The standalone scripts exercise focused behavior without PHPUnit or a live WordPress site.
E1 also adds:

```powershell
php moltex_exporter/tests/audit_inventory_regression.php
php moltex_exporter/tests/callback_path_regression.php
php moltex_exporter/tests/identity_regression.php
```

## PHPUnit coverage status

The PHPUnit suite contains behavior-focused scanner unit tests backed by WordPress mocks.
The E1 gate was green with 68 tests and 244 assertions. E2 adds registry, writer,
characterization, schema, deterministic-manifest, sample, tamper, missing-artifact,
traversal, discovery, and validation-report coverage; consult the E2 receipt for final
counts.

The former `IntegrationTest.php` was deleted because it was a second mock suite with stale
expectations, not an integration test. Real install/export/package/download coverage belongs
to the disposable WordPress smoke fixture below.

## Disposable WordPress smoke

Start Docker Desktop, then run:

```powershell
powershell -ExecutionPolicy Bypass -File moltex_exporter/tests/wordpress/run-smoke.ps1
```

The script pins WordPress 7.0.1, PHP 8.2, WP-CLI 2.10.0, and MariaDB 10.11.8. It creates
public and private fixture content, activates the plugin, performs authenticated complete and
discovery exports, exercises signed downloads, and writes ignored output under
`moltex_exporter/tests/wordpress/output/`.

## Adding coverage

Regression fixes first reproduce the failure. Keep WordPress mocks behavior-focused and only
claim live integration when the disposable WordPress fixture executed it.
