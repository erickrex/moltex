<?php
/**
 * Privacy regression for the reviewed E1 compatibility ZIP.
 *
 * Usage: php privacy_fixture_regression.php path/to/export.zip
 *
 * @package Moltex_Exporter
 */

$zip_path = isset( $argv[1] ) ? $argv[1] : dirname( __DIR__, 2 ) . '/samples/legacy-1-export.zip';
if ( ! is_file( $zip_path ) ) {
	fwrite( STDERR, 'ZIP not found: ' . $zip_path . "\n" );
	exit( 1 );
}

$zip = new ZipArchive();
if ( true !== $zip->open( $zip_path ) ) {
	fwrite( STDERR, 'Could not open ZIP: ' . $zip_path . "\n" );
	exit( 1 );
}

$forbidden = array(
	'PRIVATE-CONTENT-MUST-NOT-EXPORT',
	'SYNTHETIC-SECRET-MUST-NOT-EXPORT',
	'SYNTHETIC-OPTION-MUST-NOT-EXPORT',
	'admin@example.invalid',
	'/var/www/html',
	'/home/',
	'/srv/',
);
$text_extensions = array( 'json', 'txt', 'md', 'csv', 'html', 'css', 'js', 'php', 'sql' );
$failures = array();

for ( $index = 0; $index < $zip->numFiles; $index++ ) {
	$stat = $zip->statIndex( $index );
	if ( false === $stat || $stat['size'] <= 0 || $stat['size'] > 5 * 1024 * 1024 ) {
		continue;
	}
	$extension = strtolower( pathinfo( $stat['name'], PATHINFO_EXTENSION ) );
	if ( ! in_array( $extension, $text_extensions, true ) ) {
		continue;
	}
	$contents = $zip->getFromIndex( $index );
	foreach ( $forbidden as $needle ) {
		if ( false !== strpos( $contents, $needle ) ) {
			$failures[] = $stat['name'] . ': ' . $needle;
		}
	}
	if ( preg_match( '/["\'](?:[A-Za-z]:[\\\\\/](?:Users|Windows|Program Files)[^"\']*)["\']/', $contents ) ) {
		$failures[] = $stat['name'] . ': Windows absolute path';
	}
}

$zip->close();

if ( ! empty( $failures ) ) {
	fwrite( STDERR, "Privacy regression failed:\n- " . implode( "\n- ", array_unique( $failures ) ) . "\n" );
	exit( 1 );
}

echo 'privacy_fixture_regression: ok (' . basename( $zip_path ) . ")\n";
