<?php
/**
 * Contract enforcement at the packaging boundary.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class PackagerContractTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;
	use Moltex_Exporter_Contract_Fixture_Trait;

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

	public function test_zip_filename_contains_the_verified_site_workspace_slug() {
		global $mock_upload_dir;
		$uploads = $this->directory . '/uploads';
		mkdir( $uploads, 0755, true );
		$mock_upload_dir = array( 'basedir' => $uploads );
		try {
			$packager = new Moltex_Exporter_Packager();
			$export = $packager->create_artifacts_directory();
			$this->assertNotFalse( $export );
			$this->write_contract_fixture( $export );

			$result = $packager->create_zip( $export );

			$this->assertTrue( $result['success'], isset( $result['error'] ) ? $result['error'] : '' );
			$this->assertMatchesRegularExpression(
				'/^migration-artifacts-fixture-example-[^.]+\.zip$/',
				$result['zip_filename']
			);
		} finally {
			$mock_upload_dir = null;
		}
	}
}
