<?php
/**
 * Public frontend asset selection coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

if ( ! class_exists( 'WP_Scripts' ) ) {
	class WP_Scripts {
		public $registered = array();
		public $queue = array();
	}
}

if ( ! class_exists( 'WP_Styles' ) ) {
	class WP_Styles {
		public $registered = array();
		public $queue = array();
	}
}

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-assets-scanner.php';

class AssetsScannerTest extends TestCase {

	protected function setUp(): void {
		global $mock_filters, $wp_scripts, $wp_styles;

		$mock_filters['wp_enqueue_scripts'] = array();
		$mock_filters['admin_enqueue_scripts'] = array();

		$wp_scripts = new WP_Scripts();
		$wp_styles  = new WP_Styles();

		$wp_scripts->registered = array(
			'admin-editor' => $this->dependency( '/wp-admin/js/editor.js' ),
			'frontend-lib' => $this->dependency( '/wp-includes/js/frontend-lib.js' ),
			'frontend-app' => $this->dependency( '/wp-includes/js/frontend-app.js', array( 'frontend-lib' ) ),
			'unused-script' => $this->dependency( '/wp-includes/js/unused.js' ),
		);
		$wp_scripts->queue = array( 'admin-editor' );

		$wp_styles->registered = array(
			'admin-style' => $this->dependency( '/wp-admin/css/common.css' ),
			'frontend-style' => $this->dependency( '/wp-includes/css/frontend-style.css' ),
			'unused-style' => $this->dependency( '/wp-includes/css/unused.css' ),
		);
		$wp_styles->queue = array( 'admin-style' );
	}

	public function test_capture_includes_only_frontend_queue_and_dependency_closure() {
		global $wp_scripts, $wp_styles;
		$admin_hook_ran = false;

		add_action(
			'wp_enqueue_scripts',
			function () {
				global $wp_scripts, $wp_styles;
				$wp_scripts->queue[] = 'frontend-app';
				$wp_styles->queue[]  = 'frontend-style';
			}
		);
		add_action(
			'admin_enqueue_scripts',
			function () use ( &$admin_hook_ran ) {
				$admin_hook_ran = true;
			}
		);

		$scanner = new Moltex_Exporter_Assets_Scanner();
		$method  = new ReflectionMethod( $scanner, 'capture_frontend_assets' );
		$method->setAccessible( true );
		$assets = $method->invoke( $scanner );

		$this->assertSame( array( 'frontend-lib', 'frontend-app' ), array_keys( $assets['scripts'] ) );
		$this->assertSame( array( 'frontend-style' ), array_keys( $assets['styles'] ) );
		$this->assertSame( array( 'admin-editor' ), $wp_scripts->queue, 'The admin request script queue must be restored.' );
		$this->assertSame( array( 'admin-style' ), $wp_styles->queue, 'The admin request style queue must be restored.' );
		$this->assertTrue( $assets['scripts']['frontend-lib']['enqueued'] );
		$this->assertFalse( $admin_hook_ran, 'The scanner must not execute admin asset hooks.' );
	}

	private function dependency( $src, array $dependencies = array() ) {
		return (object) array(
			'src'   => $src,
			'deps'  => $dependencies,
			'ver'   => '1.0.0',
			'args'  => 'all',
			'extra' => array(),
		);
	}
}
