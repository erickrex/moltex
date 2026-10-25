<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-forms-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-site-options-scanner.php';

class SnippetsAndMailPoetWpdb extends Mock_WPDB {
	public $prefix = 'wp_';
	public function prepare( $query, ...$args ) {
		return $query . ' ' . implode( ' ', array_map( 'strval', $args ) );
	}
	public function get_var( $query ) {
		foreach ( array( 'wp_snippets', 'wp_mailpoet_segments' ) as $table ) {
			if ( false !== strpos( $query, $table ) ) {
				return $table;
			}
		}
		return null;
	}
	public function get_results( $query, $output = null ) {
		if ( false !== strpos( $query, 'FROM wp_snippets' ) ) {
			return array( array( 'id' => '3', 'name' => 'Hide price', 'description' => 'x', 'code' => 'add_filter("a","b");', 'tags' => 'gd, price', 'scope' => 'global', 'priority' => '10', 'active' => '1', 'modified' => '2024-01-01' ) );
		}
		if ( false !== strpos( $query, 'FROM wp_mailpoet_segments' ) ) {
			return array( array( 'id' => '1', 'name' => 'Newsletter', 'type' => 'default', 'description' => '', 'deleted_at' => null, 'subscriber_count' => '23', 'subscribed_count' => '20' ) );
		}
		if ( false !== strpos( $query, 'FROM wp_mailpoet_subscribers' ) ) {
			return array( array( 'id' => '9', 'email' => 'fan@example.com', 'status' => 'subscribed', 'created_at' => '2023-01-01', 'confirmed_at' => '2023-01-02', 'last_subscribed_at' => null, 'segment_ids' => '1' ) );
		}
		return array();
	}
}

class SnippetsAndMailPoetTest extends TestCase {
	protected function setUp(): void {
		global $wpdb;
		$wpdb = new SnippetsAndMailPoetWpdb();
	}

	protected function tearDown(): void {
		update_option( 'moltex_settings', array() );
	}

	private function call( $object, $method ) {
		$reflection = new ReflectionMethod( $object, $method );
		$reflection->setAccessible( true );
		return $reflection->invoke( $object );
	}

	public function test_code_snippets_are_exported_for_review_only() {
		$snippets = $this->call( new Moltex_Exporter_Site_Options_Scanner(), 'get_code_snippets' );
		$this->assertSame( 'never_execute', $snippets['execution'] );
		$this->assertSame( 'Hide price', $snippets['snippets'][0]['name'] );
		$this->assertTrue( $snippets['snippets'][0]['active'] );
		$this->assertSame( array( 'gd', 'price' ), $snippets['snippets'][0]['tags'] );
		$this->assertSame( 'add_filter("a","b");', $snippets['snippets'][0]['code'] );
	}

	public function test_mailpoet_lists_always_subscribers_only_with_opt_in() {
		$forms = new Moltex_Exporter_Forms_Scanner();
		$default = $this->call( $forms, 'export_mailpoet' );
		$this->assertSame( 23, $default['lists'][0]['subscriber_count'] );
		$this->assertSame( 'not_exported_without_opt_in', $default['subscribers'] );

		update_option( 'moltex_settings', array( 'include_subscribers' => '1' ) );
		$opted = $this->call( $forms, 'export_mailpoet' );
		$this->assertSame( 'fan@example.com', $opted['subscribers'][0]['email'] );
		$this->assertSame( array( 1 ), $opted['subscribers'][0]['list_ids'] );
		$this->assertSame( '2023-01-02', $opted['subscribers'][0]['consent_date'] );
	}
}
