<?php
/**
 * Contract enforcement at the packaging boundary.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class PackagerContractTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-packager-contract' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_packaging_refuses_an_export_without_bundle_manifest() {
		file_put_contents( $this->directory . '/legacy.json', "{}\n" );

		$result = ( new Moltex_Exporter_Packager() )->create_zip( $this->directory );

		$this->assertFalse( $result['success'] );
		$this->assertStringContainsString( 'Required bundle.json is missing', $result['error'] );
	}
}
