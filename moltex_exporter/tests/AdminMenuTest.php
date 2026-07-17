<?php
/**
 * Admin menu compatibility coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class AdminMenuTest extends TestCase {

	protected function setUp(): void {
		global $mock_removed_menu_pages;
		$mock_removed_menu_pages = array();
	}

	public function test_removes_only_the_obsolete_djamingo_menu() {
		global $mock_removed_menu_pages;

		$admin = new Moltex_Exporter_Admin_Page();
		$admin->remove_legacy_admin_menu();

		$this->assertSame( array( 'djamingo-exporter' ), $mock_removed_menu_pages );
	}

	public function test_legacy_cleanup_runs_after_normal_admin_menu_registration() {
		$source = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-admin-page.php' );

		$this->assertStringContainsString(
			"add_action( 'admin_menu', array( \$this, 'remove_legacy_admin_menu' ), PHP_INT_MAX );",
			$source
		);
	}
}
