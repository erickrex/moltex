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

	private function make_zip( $name, array $entries ) {
		$zip_path = $this->directory . '/' . $name;
		$zip = new ZipArchive();
		$zip->open( $zip_path, ZipArchive::CREATE );
		foreach ( $entries as $entry => $content ) {
			$zip->addFromString( $entry, $content );
		}
		$zip->close();
		return $zip_path;
	}

	private function split( $zip_path, $limit ) {
		$method = new ReflectionMethod( 'Moltex_Exporter_Packager', 'split_into_parts' );
		$method->setAccessible( true );
		return $method->invoke( new Moltex_Exporter_Packager(), $zip_path, $limit );
	}

	/**
	 * Rebuild every part from its downloads, extract, and return name => bytes.
	 */
	private function reassemble( array $result ) {
		$files = array();
		foreach ( $result['parts'] as $part ) {
			$bytes = '';
			foreach ( $part['downloads'] as $download ) {
				$path = $this->directory . '/' . $download['filename'];
				$this->assertFileExists( $path );
				$this->assertSame( $download['sha256'], hash_file( 'sha256', $path ) );
				$bytes .= file_get_contents( $path );
			}
			$this->assertSame( $part['sha256'], hash( 'sha256', $bytes ) );
			$rebuilt = $this->directory . '/rebuilt-' . $part['label'] . '.zip';
			file_put_contents( $rebuilt, $bytes );
			$zip = new ZipArchive();
			$this->assertTrue( $zip->open( $rebuilt ) );
			for ( $i = 0; $i < $zip->numFiles; $i++ ) {
				$name = $zip->getNameIndex( $i );
				$this->assertArrayNotHasKey( $name, $files, 'entry appears in two parts' );
				$files[ $name ] = $zip->getFromIndex( $i );
			}
			$zip->close();
		}
		ksort( $files );
		return $files;
	}

	private function assert_every_download_fits( array $result, $limit ) {
		foreach ( $result['parts'] as $part ) {
			foreach ( $part['downloads'] as $download ) {
				$this->assertLessThanOrEqual( $limit, filesize( $this->directory . '/' . $download['filename'] ), $download['filename'] );
			}
		}
	}

	public function test_bundle_is_split_into_data_and_media_parts_that_reassemble_exactly() {
		$entries = array(
			'bundle.json'     => '{}',
			'content/a.json'  => '{"a":1}',
			'media/one.bin'   => random_bytes( 3500 ),
			'media/two.bin'   => random_bytes( 3500 ),
			'media/three.bin' => random_bytes( 9000 ),
		);
		$zip_path = $this->make_zip( 'bundle-x.zip', $entries );

		$result = $this->split( $zip_path, 8500 );

		$this->assertSame( array( 'data', 'media-01', 'media-02' ), array_column( $result['parts'], 'label' ) );
		$this->assertSame( array( 'bundle.json', 'content/a.json' ), $result['parts'][0]['files'] );
		$this->assertSame( array( 'media/one.bin', 'media/two.bin' ), $result['parts'][1]['files'] );
		// The single 9000-byte entry cannot fit, so its part is cut into chunks.
		$this->assertTrue( $result['parts'][2]['chunked'] );
		$this->assertCount( 2, $result['parts'][2]['downloads'] );
		$this->assertFileDoesNotExist( $this->directory . '/' . $result['parts'][2]['filename'] );
		$this->assert_every_download_fits( $result, 8500 );
		ksort( $entries );
		$this->assertSame( $entries, $this->reassemble( $result ) );
		$index = json_decode( file_get_contents( $result['index_path'] ), true );
		$this->assertSame( 'bundle-x.zip', $index['bundle_zip'] );
	}

	public function test_interleaved_media_and_data_entries_are_covered() {
		// Regression: coverage used to compare ordered lists, so data after media failed.
		$entries = array(
			'content/a.json'     => '{"a":1}',
			'media/a.jpg'        => random_bytes( 2000 ),
			'site_settings.json' => '{"s":1}',
			'bundle.json'        => '{}',
		);
		$result = $this->split( $this->make_zip( 'bundle-i.zip', $entries ), 100000 );

		$this->assertSame( array( 'data', 'media-01' ), array_column( $result['parts'], 'label' ) );
		$this->assertSame( 'bundle.json', $result['parts'][0]['files'][0] );
		ksort( $entries );
		$this->assertSame( $entries, $this->reassemble( $result ) );
	}

	public function test_part_archives_stay_under_limit_including_zip_overhead() {
		// Regression: 4000 + 4500 incompressible bytes under an 8500 limit gave an 8726-byte part.
		$entries = array(
			'bundle.json'   => '{}',
			'media/one.bin' => random_bytes( 4000 ),
			'media/two.bin' => random_bytes( 4500 ),
		);
		$result = $this->split( $this->make_zip( 'bundle-o.zip', $entries ), 8500 );

		$this->assert_every_download_fits( $result, 8500 );
		foreach ( $result['parts'] as $part ) {
			$this->assertFalse( $part['chunked'], $part['label'] );
		}
		ksort( $entries );
		$this->assertSame( $entries, $this->reassemble( $result ) );
	}

	public function test_oversized_data_is_split_into_several_data_parts() {
		$entries = array( 'bundle.json' => '{}' );
		for ( $i = 0; $i < 6; $i++ ) {
			$entries[ 'content/item-' . $i . '.json' ] = bin2hex( random_bytes( 1500 ) );
		}
		$result = $this->split( $this->make_zip( 'bundle-d.zip', $entries ), 5000 );

		$labels = array_column( $result['parts'], 'label' );
		$this->assertSame( 'data', $labels[0] );
		$this->assertContains( 'data-02', $labels );
		$this->assertSame( 'bundle.json', $result['parts'][0]['files'][0] );
		$this->assert_every_download_fits( $result, 5000 );
		ksort( $entries );
		$this->assertSame( $entries, $this->reassemble( $result ) );
	}
}
