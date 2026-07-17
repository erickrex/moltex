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
$patterns   = array(
	'Strapi',
	'Digital Ocean',
	'ChatGPT Sites',
	'Export with AI Agents',
	'modern Python architecture using AI Agents',
	'with Codex',
);
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

$admin_class = file_get_contents( $plugin_dir . '/includes/class-admin-page.php' );
$template    = file_get_contents( $plugin_dir . '/templates/admin-page.php' );
if (
	substr_count( $admin_class, "'Moltex Exporter'" ) < 2
	|| false === strpos( $admin_class, "'Export blueprints'" )
	|| false === strpos( $template, "'Export blueprint'" )
	|| false === strpos( $template, 'Astro' )
) {
	fwrite( STDERR, "Current Moltex Exporter labels are missing.\n" );
	exit( 1 );
}

echo "identity_regression: ok\n";
