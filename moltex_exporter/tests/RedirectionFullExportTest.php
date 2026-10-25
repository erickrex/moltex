<?php

use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-redirects-scanner.php';

class RedirectionFullExportWpdb extends Mock_WPDB {
	public $prefix = 'wp_';
	public function prepare( $query, ...$args ) {
		return $query . ' ' . implode( ' ', array_map( 'strval', $args ) );
	}
	public function get_var( $query ) {
		foreach ( array( 'wp_redirection_items', 'wp_redirection_groups', 'wp_redirection_404' ) as $table ) {
			if ( false !== strpos( $query, $table ) ) {
				return $table;
			}
		}
		return null;
	}
	public function get_results( $query, $output = null ) {
		if ( false !== strpos( $query, 'redirection_groups' ) ) {
			return array( array( 'id' => '1', 'name' => 'Legacy', 'module_id' => '1', 'status' => 'enabled', 'position' => '0' ) );
		}
		if ( false !== strpos( $query, 'redirection_404' ) ) {
			return array( array( 'url' => '/old-club/', 'hits' => '42', 'last_seen' => '2026-09-01 10:00:00', 'ip' => '192.0.2.1' ) );
		}
		if ( false !== strpos( $query, "status = 'enabled'" ) ) {
			return array( array( 'url' => '/a/', 'action_data' => '/b/', 'action_code' => '301', 'regex' => '0', 'status' => 'enabled' ) );
		}
		if ( false !== strpos( $query, 'redirection_items' ) ) {
			return array(
				array( 'id' => '1', 'url' => '/a/', 'match_type' => 'url', 'action_type' => 'url', 'action_code' => '301', 'action_data' => '/b/', 'regex' => '0', 'status' => 'enabled', 'group_id' => '1', 'last_count' => '7' ),
				array( 'id' => '2', 'url' => '/c/', 'match_type' => 'login', 'action_type' => 'url', 'action_code' => '302', 'action_data' => '{"logged_in":"/in/","logged_out":"/out/"}', 'regex' => '0', 'status' => 'disabled', 'group_id' => '1', 'last_count' => '0' ),
			);
		}
		return array();
	}
}

class RedirectionFullExportTest extends TestCase {
	private $previous;

	protected function setUp(): void {
		global $wpdb;
		$this->previous = $wpdb;
		$wpdb = new RedirectionFullExportWpdb();
	}

	protected function tearDown(): void {
		global $wpdb;
		$wpdb = $this->previous;
	}

	public function test_all_statuses_groups_and_aggregated_404s_are_exported_without_ip() {
		$scanner = new Moltex_Exporter_Redirects_Scanner( array( 'context' => array( 'content' => array() ) ) );
		$method = new ReflectionMethod( $scanner, 'export_plugin_redirects' );
		$method->setAccessible( true );
		$plugin_redirects = $method->invoke( $scanner );
		$full = $plugin_redirects['redirection_full'];

		$this->assertCount( 1, $plugin_redirects['redirection'] );
		$this->assertCount( 2, $full['items'] );
		$this->assertSame( array( 'disabled' => 1, 'enabled' => 1 ), $full['counts']['by_status'] );
		$this->assertSame( array( 'logged_in' => '/in/', 'logged_out' => '/out/' ), $full['items'][1]['action_data'] );
		$this->assertSame( 'Legacy', $full['groups'][0]['name'] );
		$this->assertSame( 42, $full['not_found'][0]['hits'] );
		$this->assertArrayNotHasKey( 'ip', $full['not_found'][0] );
	}
}
