<?php
/**
 * Explicit maintainer command for rebuilding the synthetic E2 sample.
 * Tests never invoke this script or regenerate their oracle.
 *
 * @package Moltex_Exporter
 */

require_once __DIR__ . '/bootstrap.php';

class Moltex_Exporter_Sample_Builder {
	use Moltex_Exporter_Contract_Fixture_Trait;

	public function build( $sample_path ) {
		$directory = sys_get_temp_dir() . '/moltex-e2-sample-' . bin2hex( random_bytes( 6 ) );
		mkdir( $directory, 0755, true );
		try {
			$manifest = $this->write_contract_fixture( $directory );
			$this->zip_contract_fixture( $directory, $sample_path );
			return $manifest['bundle_id'];
		} finally {
			$iterator = new RecursiveIteratorIterator(
				new RecursiveDirectoryIterator( $directory, FilesystemIterator::SKIP_DOTS ),
				RecursiveIteratorIterator::CHILD_FIRST
			);
			foreach ( $iterator as $item ) {
				$item->isDir() ? rmdir( $item->getPathname() ) : unlink( $item->getPathname() );
			}
			rmdir( $directory );
		}
	}
}

$sample_path = dirname( __DIR__, 2 ) . '/samples/moltex-export-1.zip';
$bundle_id = ( new Moltex_Exporter_Sample_Builder() )->build( $sample_path );
fwrite( STDOUT, $bundle_id . "\n" );
