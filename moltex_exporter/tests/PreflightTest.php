<?php
/**
 * Live-site preflight classification coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class PreflightTest extends TestCase {

	public function test_missing_zip_or_unwritable_uploads_block_export() {
		$preflight = new Moltex_Exporter_Preflight(
			array(
				'zip_available'    => false,
				'uploads'          => array( 'basedir' => '/fixture', 'error' => false ),
				'uploads_writable' => false,
				'memory_limit'     => '256M',
				'max_execution_time' => 120,
				'disk_free_bytes'  => 536870912,
			)
		);
		$result = $preflight->evaluate( array( 'export_mode' => 'discovery' ) );

		$this->assertFalse( $result['ready'] );
		$this->assertCount( 2, $result['blockers'] );
	}

	public function test_operational_limits_and_missing_evidence_are_warnings() {
		global $mock_options;
		$mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] = array();
		$preflight = new Moltex_Exporter_Preflight(
			array(
				'zip_available'    => true,
				'uploads'          => array( 'basedir' => '/fixture', 'error' => false ),
				'uploads_writable' => true,
				'memory_limit'     => '128M',
				'max_execution_time' => 30,
				'disk_free_bytes'  => 1024,
			)
		);
		$result = $preflight->evaluate( array( 'export_mode' => 'complete', 'include_html_snapshots' => false ) );

		$this->assertTrue( $result['ready'] );
		$this->assertCount( 5, $result['warnings'] );
	}

	public function test_admin_settings_default_complete_exports_to_snapshots() {
		$settings = ( new Moltex_Exporter_Admin_Page() )->sanitize_settings( array( 'export_mode' => 'complete' ) );
		$this->assertTrue( $settings['include_html_snapshots'] );
		$this->assertFalse( $settings['include_private_content'] );
	}

	public function test_unsupported_site_capabilities_warn_without_blocking() {
		global $mock_options;
		$mock_options['active_plugins'] = array( 'woocommerce/woocommerce.php' );
		$mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] = array( array( 'attachment_id' => 1 ) );
		$preflight = new Moltex_Exporter_Preflight(
			array(
				'zip_available'      => true,
				'uploads'            => array( 'basedir' => '/fixture', 'error' => false ),
				'uploads_writable'   => true,
				'memory_limit'       => '256M',
				'max_execution_time' => 120,
				'disk_free_bytes'    => 536870912,
			)
		);
		$result = $preflight->evaluate( array( 'export_mode' => 'complete', 'include_html_snapshots' => true ) );

		$this->assertTrue( $result['ready'] );
		$this->assertSame( array( 'WooCommerce is outside the initial static migration profile.' ), $result['warnings'] );
		$mock_options = array();
	}
}
