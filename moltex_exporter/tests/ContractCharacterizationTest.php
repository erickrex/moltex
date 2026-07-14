<?php
/**
 * Reviewed pre-writer artifact characterization.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ContractCharacterizationTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;
	use Moltex_Exporter_Contract_Fixture_Trait;

	private $directory;
	private $characterization;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-characterization' );
		$this->characterization = json_decode(
			file_get_contents( __DIR__ . '/fixtures/e2/required-artifact-characterization.json' ),
			true
		);
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_registry_preserves_reviewed_required_producer_paths() {
		$paths = array_values(
			array_filter(
				( new Moltex_Exporter_Artifact_Registry() )->get_required_paths( false ),
				function( $path ) {
					return 0 !== strpos( $path, 'schemas/' );
				}
			)
		);
		sort( $paths, SORT_STRING );

		$this->assertSame( $this->characterization['required_producer_artifacts'], $paths );
	}

	public function test_writer_preserves_reviewed_semantic_key_surface() {
		$this->write_contract_fixture( $this->directory );

		foreach ( $this->characterization['semantic_keys'] as $path => $expected_keys ) {
			$data = json_decode( file_get_contents( $this->directory . '/' . $path ), true );
			$keys = is_array( $data ) ? array_keys( $data ) : array();
			sort( $keys, SORT_STRING );
			$this->assertSame( $expected_keys, $keys, $path );
		}
	}
}
