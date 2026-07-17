<?php
/**
 * Child process fixture for download streaming regression coverage.
 */

define( 'WPINC', 'wp-includes' );
define( 'ABSPATH', dirname( __DIR__, 2 ) . '/' );

function wp_die( $message ) {
	fwrite( STDERR, $message );
	exit( 1 );
}

require_once dirname( __DIR__, 2 ) . '/includes/trait-error-logger.php';
require_once dirname( __DIR__, 2 ) . '/includes/class-packager.php';

$reflection = new ReflectionClass( 'Moltex_Exporter_Packager' );
$packager   = $reflection->newInstanceWithoutConstructor();

ob_start();
echo 'outer-buffer-contamination';
ob_start();
echo 'inner-buffer-contamination';

$packager->serve_download( $argv[1], 'fixture.zip' );
