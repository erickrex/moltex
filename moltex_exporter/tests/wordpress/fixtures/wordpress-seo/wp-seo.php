<?php
/**
 * Plugin Name: Golden Path SEO Evidence Adapter
 * Description: Exposes reviewed Yoast-compatible metadata to the exporter fixture.
 * Version: 1.0.0
 *
 * This fixture does not emulate Yoast runtime behavior. It identifies the deliberately
 * seeded Yoast-compatible post metadata so the SEO scanner exercises its real adapter.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'WPSEO_VERSION', 'golden-path-fixture-1.0.0' );
