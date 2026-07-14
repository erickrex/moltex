<?php
/**
 * Immutable synthetic moltex-export/1 sample coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ContractSampleTest extends TestCase {

	public function test_checked_in_sample_and_expected_bundle_id_validate() {
		$sample = dirname( MOLTEX_PLUGIN_DIR ) . '/samples/moltex-export-1.zip';
		$expected = trim( file_get_contents( dirname( MOLTEX_PLUGIN_DIR ) . '/samples/moltex-export-1.bundle-id.txt' ) );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $sample );

		$this->assertTrue( $result['valid'], implode( "\n", $result['errors'] ) );
		$this->assertSame( $expected, $result['bundle_id'] );
		$this->assertTrue( $result['complete_migration_eligible'] );
	}
}
