<?php
/**
 * Validated writer tests.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ArtifactWriterTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;
	use Moltex_Exporter_Contract_Fixture_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-writer' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_fixture_writes_a_deterministic_manifest_and_schemas() {
		$first = $this->write_contract_fixture( $this->directory );

		$this->assertMatchesRegularExpression( '/^sha256:[a-f0-9]{64}$/', $first['bundle_id'] );
		$this->assertFileExists( $this->directory . '/bundle.json' );
		$this->assertFileExists( $this->directory . '/privacy-scan.json' );
		$this->assertFileExists( $this->directory . '/schemas/content-item.schema.json' );
		$this->assertSame( 'E2 Fixture', $first['site_identity']['site_name'] );
		$this->assertSame( 'fixture.example', $first['site_identity']['domain'] );
		$this->assertSame( 'fixture-example', $first['site_identity']['workspace_slug'] );
		$this->assertSame( 'pass', $first['privacy']['secret_scan'] );
		$this->assertSame( 'privacy-scan.json', $first['privacy']['secret_scan_receipt']['path'] );
		$this->assertMatchesRegularExpression(
			'/^[a-f0-9]{64}$/',
			$first['privacy']['secret_scan_receipt']['sha256']
		);
		$paths = array_column( $first['artifacts'], 'path' );
		$sorted = $paths;
		sort( $sorted, SORT_STRING );
		$this->assertSame( $sorted, $paths );
	}

	public function test_schema_violation_fails_before_a_file_is_written() {
		$writer = new Moltex_Exporter_Artifact_Writer( $this->directory );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( 'Schema validation failed' );
		$writer->write_json( 'content/post/broken.json', array( 'slug' => 'broken' ), 'content' );
	}

	public function test_finalize_rejects_a_missing_required_artifact() {
		$writer = new Moltex_Exporter_Artifact_Writer( $this->directory );
		$writer->write_json( 'menus.json', array( 'menu_locations' => array(), 'menus' => array() ), 'menus' );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( 'Required artifact is missing' );
		$writer->finalize_bundle( array() );
	}

	public function test_duplicate_normalized_path_is_rejected() {
		$writer = new Moltex_Exporter_Artifact_Writer( $this->directory );
		$data = array( 'menu_locations' => array(), 'menus' => array() );
		$writer->write_json( 'menus.json', $data, 'menus' );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( 'Duplicate normalized artifact path' );
		$writer->write_json( './menus.json', $data, 'menus' );
	}

	public function test_atomic_replace_failure_includes_producer_and_path() {
		mkdir( $this->directory . '/menus.json' );
		$writer = new Moltex_Exporter_Artifact_Writer( $this->directory );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( '[menus] menus.json: Atomic replace failed.' );
		$writer->write_json( 'menus.json', array( 'menu_locations' => array(), 'menus' => array() ), 'menus' );
	}

	public function test_malformed_utf8_includes_producer_and_path() {
		$writer = new Moltex_Exporter_Artifact_Writer( $this->directory );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( '[content] content/post/invalid.json' );
		$writer->write_json(
			'content/post/invalid.json',
			array( 'id' => 1, 'type' => 'post', 'slug' => 'invalid', 'status' => 'publish', 'title' => "\xB1\x31" ),
			'content'
		);
	}

	public function test_unchanged_exports_have_equivalent_normalized_manifests() {
		$second_directory = $this->create_temp_directory( 'moltex-writer-second' );
		try {
			$first = $this->write_contract_fixture( $this->directory );
			$second = $this->write_contract_fixture( $second_directory );

			$this->assertSame( $first['bundle_id'], $second['bundle_id'] );
			$this->assertSame( $first, $second );
		} finally {
			$this->remove_temp_directory( $second_directory );
		}
	}
}
