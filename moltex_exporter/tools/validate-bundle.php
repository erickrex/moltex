<?php
/**
 * Validate a moltex-export/1 ZIP without extracting it.
 *
 * Usage: php tools/validate-bundle.php path/to/export.zip
 *
 * @package Moltex_Exporter
 */

if ( PHP_SAPI !== 'cli' ) {
	exit( 2 );
}
if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

require_once dirname( __DIR__ ) . '/includes/class-artifact-registry.php';
require_once dirname( __DIR__ ) . '/includes/class-schema-validator.php';
require_once dirname( __DIR__ ) . '/includes/class-bundle-validator.php';

if ( 2 !== $argc || ! class_exists( 'ZipArchive' ) ) {
	$result = array(
		'valid'  => false,
		'errors' => array( 2 !== $argc ? 'Expected exactly one ZIP path.' : 'PHP ZipArchive extension is unavailable.' ),
	);
	fwrite( STDOUT, json_encode( $result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES ) . "\n" );
	exit( 2 );
}

$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $argv[1] );
fwrite( STDOUT, json_encode( $result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES ) . "\n" );
exit( ! empty( $result['valid'] ) ? 0 : 1 );
