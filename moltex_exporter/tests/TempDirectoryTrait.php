<?php
/**
 * Temporary directory helpers for exporter tests.
 *
 * @package Moltex_Exporter
 */

trait Moltex_Exporter_Temp_Directory_Trait {

	/**
	 * Create a unique temporary directory.
	 *
	 * @param string $prefix Directory prefix.
	 * @return string
	 */
	private function create_temp_directory( $prefix ) {
		$path = sys_get_temp_dir() . DIRECTORY_SEPARATOR . $prefix . '-' . bin2hex( random_bytes( 6 ) );
		if ( ! mkdir( $path, 0755, true ) && ! is_dir( $path ) ) {
			throw new RuntimeException( 'Unable to create test directory: ' . $path );
		}

		return $path;
	}

	/**
	 * Remove a test-owned temporary directory.
	 *
	 * @param string $path Directory to remove.
	 */
	private function remove_temp_directory( $path ) {
		if ( ! is_dir( $path ) ) {
			return;
		}

		$iterator = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator( $path, FilesystemIterator::SKIP_DOTS ),
			RecursiveIteratorIterator::CHILD_FIRST
		);

		foreach ( $iterator as $item ) {
			if ( $item->isDir() ) {
				rmdir( $item->getPathname() );
			} else {
				unlink( $item->getPathname() );
			}
		}

		rmdir( $path );
	}
}
