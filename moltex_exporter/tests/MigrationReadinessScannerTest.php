<?php

use PHPUnit\Framework\TestCase;

class MigrationReadinessScannerTest extends TestCase {

	protected function setUp(): void {
		parent::setUp();
		global $mock_options;
		$mock_options['active_plugins'] = array();
	}

	public function test_basic_site_is_eligible() {
		$scanner = new Moltex_Exporter_Migration_Readiness_Scanner(
			array(
				'context' => array(
					'content' => array(
						'completeness' => array( 'complete' => true ),
					),
				),
			)
		);

		$result = $scanner->scan();

		$this->assertTrue( $result['eligible'] );
		$this->assertEmpty( $result['blockers'] );
	}

	public function test_ecommerce_site_is_blocked() {
		global $mock_options;
		$mock_options['active_plugins'] = array( 'woocommerce/woocommerce.php' );
		$scanner = new Moltex_Exporter_Migration_Readiness_Scanner(
			array(
				'context' => array(
					'content' => array(
						'completeness' => array( 'complete' => true ),
					),
				),
			)
		);

		$result = $scanner->scan();

		$this->assertFalse( $result['eligible'] );
		$this->assertSame( 'ecommerce', $result['blockers'][0]['category'] );
	}

	public function test_incomplete_export_is_blocked() {
		$scanner = new Moltex_Exporter_Migration_Readiness_Scanner(
			array(
				'context' => array(
					'content' => array(
						'completeness' => array( 'complete' => false ),
					),
				),
			)
		);

		$result = $scanner->scan();

		$this->assertFalse( $result['eligible'] );
		$this->assertSame( 'incomplete_content_export', $result['blockers'][0]['code'] );
	}
}
