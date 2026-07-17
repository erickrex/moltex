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

	public function test_operational_limits_and_disabled_html_are_warnings() {
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
		$this->assertCount( 4, $result['warnings'] );
		$this->assertNotContains( 'No reviewed desktop/mobile reference screenshots are registered.', $result['warnings'] );
	}

	public function test_admin_settings_default_complete_exports_to_snapshots() {
		$settings = ( new Moltex_Exporter_Admin_Page() )->sanitize_settings( array( 'export_mode' => 'complete' ) );
		$this->assertTrue( $settings['include_html_snapshots'] );
		$this->assertSame( 'bounded', $settings['html_snapshot_mode'] );
		$this->assertFalse( $settings['include_private_content'] );
	}

	public function test_snapshot_mode_accepts_bounded_off_and_all_only() {
		$admin = new Moltex_Exporter_Admin_Page();

		$this->assertSame( 'off', $admin->sanitize_settings( array( 'html_snapshot_mode' => 'off' ) )['html_snapshot_mode'] );
		$this->assertSame( 'all', $admin->sanitize_settings( array( 'html_snapshot_mode' => 'all' ) )['html_snapshot_mode'] );
		$this->assertSame( 'bounded', $admin->sanitize_settings( array( 'html_snapshot_mode' => 'invalid' ) )['html_snapshot_mode'] );
	}

	public function test_unsupported_site_capabilities_warn_without_blocking() {
		global $mock_options;
		$mock_options['active_plugins'] = array( 'woocommerce/woocommerce.php' );
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

	public function test_ajax_scan_prepares_admin_screen_for_wordpress_59_filters() {
		global $mock_current_screen;
		$mock_current_screen = null;
		$method = new ReflectionMethod( Moltex_Exporter_Admin_Page::class, 'prepare_ajax_admin_screen' );
		$method->setAccessible( true );
		$method->invoke( new Moltex_Exporter_Admin_Page() );

		$this->assertSame( 'toplevel_page_moltex-exporter', $mock_current_screen->id );
		$mock_current_screen = null;
	}
}
