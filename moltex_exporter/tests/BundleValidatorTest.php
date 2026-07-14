<?php
/**
 * Standalone bundle validator tests.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class BundleValidatorTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;
	use Moltex_Exporter_Contract_Fixture_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-validator' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_valid_bundle_passes_without_extraction() {
		$this->write_contract_fixture( $this->directory );
		$zip_path = $this->directory . '/fixture.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );

		$this->assertTrue( $result['valid'], implode( "\n", $result['errors'] ) );
		$this->assertSame( Moltex_Exporter_Artifact_Registry::CONTRACT_VERSION, $result['contract'] );
		$this->assertTrue( $result['complete_migration_eligible'] );
		$report_schema = MOLTEX_PLUGIN_DIR . '/schemas/moltex-export-1/schema-validation-report.schema.json';
		$this->assertSame( array(), ( new Moltex_Exporter_Schema_Validator() )->validate_file( $result, $report_schema ) );
	}

	public function test_discovery_bundle_is_valid_but_not_complete_migration_evidence() {
		$this->write_contract_fixture( $this->directory, 'discovery' );
		$zip_path = $this->directory . '/discovery.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );

		$this->assertTrue( $result['valid'], implode( "\n", $result['errors'] ) );
		$this->assertFalse( $result['complete_migration_eligible'] );
	}

	public function test_checksum_and_schema_mutation_is_localized() {
		$this->write_contract_fixture( $this->directory );
		file_put_contents( $this->directory . '/content/post/fixture-post.json', "{\"slug\":\"mutated\"}\n" );
		$zip_path = $this->directory . '/mutated.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );
		$errors = implode( ' ', $result['errors'] );

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'Artifact checksum mismatch: content/post/fixture-post.json', $errors );
		$this->assertStringContainsString( 'content/post/fixture-post.json:', $errors );
	}

	public function test_missing_required_artifact_is_rejected() {
		$this->write_contract_fixture( $this->directory );
		unlink( $this->directory . '/site_settings.json' );
		$zip_path = $this->directory . '/missing.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'Manifest artifact is missing from ZIP: site_settings.json', implode( ' ', $result['errors'] ) );
	}

	public function test_traversal_entry_is_rejected() {
		$this->write_contract_fixture( $this->directory );
		$zip_path = $this->directory . '/traversal.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );
		$zip = new ZipArchive();
		$zip->open( $zip_path );
		$zip->addFromString( '../outside.txt', 'unsafe' );
		$zip->close();

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'Unsafe ZIP entry', implode( ' ', $result['errors'] ) );
	}

	public function test_case_insensitive_duplicate_entry_is_rejected() {
		$this->write_contract_fixture( $this->directory );
		$zip_path = $this->directory . '/duplicate.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );
		$zip = new ZipArchive();
		$zip->open( $zip_path );
		$zip->addFromString( 'MENUS.JSON', "{}\n" );
		$zip->close();

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $zip_path );

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'Duplicate normalized ZIP entry', implode( ' ', $result['errors'] ) );
	}

	public function test_declared_entry_size_limit_is_enforced() {
		$this->write_contract_fixture( $this->directory );
		$zip_path = $this->directory . '/oversized.zip';
		$this->zip_contract_fixture( $this->directory, $zip_path );
		$registry = new class() extends Moltex_Exporter_Artifact_Registry {
			public function get_definition( $path ) {
				$definition = parent::get_definition( $path );
				if ( 'content/post/fixture-post.json' === $path ) {
					$definition['max_bytes'] = 4;
				}
				return $definition;
			}
		};

		$result = ( new Moltex_Exporter_Bundle_Validator( $registry ) )->validate_zip( $zip_path );

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'ZIP entry exceeds its declared byte limit', implode( ' ', $result['errors'] ) );
	}
}
