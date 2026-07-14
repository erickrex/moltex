<?php
/**
 * Regression check for stale user-facing product identity.
 *
 * @package Moltex_Exporter
 */

$plugin_dir = dirname( __DIR__ );
$files      = array(
	$plugin_dir . '/moltex_exporter.php',
	$plugin_dir . '/README.md',
	$plugin_dir . '/tests/README.md',
	$plugin_dir . '/templates/admin-page.php',
	$plugin_dir . '/includes/class-admin-page.php',
	$plugin_dir . '/includes/scanners/class-migration-readiness-scanner.php',
);
$patterns   = array( 'Strapi', 'Digital Ocean', 'ChatGPT Sites' );
$failures   = array();

foreach ( $files as $file ) {
	$contents = file_get_contents( $file );
	foreach ( $patterns as $pattern ) {
		if ( false !== stripos( $contents, $pattern ) ) {
			$failures[] = str_replace( $plugin_dir . '/', '', str_replace( '\\', '/', $file ) ) . ': ' . $pattern;
		}
	}
}

if ( ! empty( $failures ) ) {
	fwrite( STDERR, "Stale user-facing identity found:\n- " . implode( "\n- ", $failures ) . "\n" );
	exit( 1 );
}

echo "identity_regression: ok\n";
