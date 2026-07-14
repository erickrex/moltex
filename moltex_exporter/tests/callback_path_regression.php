<?php
/**
 * Regression coverage for callback source path privacy.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', '/var/www/html/' );
}
if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}
if ( ! defined( 'WP_PLUGIN_DIR' ) ) {
	define( 'WP_PLUGIN_DIR', '/var/www/html/wp-content/plugins' );
}

require_once dirname( __DIR__ ) . '/includes/class-callback-resolver.php';

function assert_same( $expected, $actual, $message ) {
	if ( $expected !== $actual ) {
		fwrite( STDERR, $message . "\nExpected: " . $expected . "\nActual: " . $actual . "\n" );
		exit( 1 );
	}
}

assert_same(
	'wp-includes/media.php',
	Moltex_Exporter_Callback_Resolver::normalize_file_path( '/var/www/html/wp-includes/media.php' ),
	'WordPress core callback paths must be ZIP-safe logical paths.'
);
assert_same(
	'plugins/example/example.php',
	Moltex_Exporter_Callback_Resolver::normalize_file_path( '/var/www/html/wp-content/plugins/example/example.php' ),
	'Plugin callback paths must not expose the server document root.'
);
assert_same(
	'external/vendor.php',
	Moltex_Exporter_Callback_Resolver::normalize_file_path( '/srv/private/vendor.php' ),
	'External callback paths must expose only a basename.'
);

echo "callback_path_regression: ok\n";
