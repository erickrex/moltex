<?php
/**
 * Behavior-focused privacy filter coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class SecurityFiltersTest extends TestCase {

	public function test_filters_sensitive_options_at_all_depths() {
		$filtered = Moltex_Exporter_Security_Filters::filter_options(
			array(
				'blogname' => 'Fixture',
				'api_key'  => 'secret',
				'nested'   => array(
					'client_secret' => 'secret',
					'public_value'  => 'safe',
				),
			)
		);

		$this->assertSame( 'Fixture', $filtered['blogname'] );
		$this->assertArrayNotHasKey( 'api_key', $filtered );
		$this->assertArrayNotHasKey( 'client_secret', $filtered['nested'] );
		$this->assertSame( 'safe', $filtered['nested']['public_value'] );
	}

	public function test_filters_prefixed_and_unprefixed_pii_meta() {
		$filtered = Moltex_Exporter_Security_Filters::filter_post_meta(
			array(
				'_billing_email' => 'private@example.invalid',
				'billing_email'  => 'private@example.invalid',
				'public_label'   => 'safe',
			)
		);

		$this->assertArrayNotHasKey( '_billing_email', $filtered );
		$this->assertArrayNotHasKey( 'billing_email', $filtered );
		$this->assertSame( 'safe', $filtered['public_label'] );
	}

	public function test_recursive_filter_removes_pii_and_temporary_keys() {
		$filtered = Moltex_Exporter_Security_Filters::filter_options(
			array(
				'nested' => array(
					'_customer_phone' => '555-555-5555',
					'_transient_cache' => 'temporary',
					'public_value'     => 'safe',
				),
			)
		);

		$this->assertArrayNotHasKey( '_customer_phone', $filtered['nested'] );
		$this->assertArrayNotHasKey( '_transient_cache', $filtered['nested'] );
		$this->assertSame( 'safe', $filtered['nested']['public_value'] );
	}

	public function test_shared_export_meta_policy_normalizes_wordpress_values() {
		$filtered = Moltex_Exporter_Security_Filters::filter_export_meta(
			array(
				'_edit_lock'       => array( '1700000000:1' ),
				'_billing_email'   => array( 'private@example.invalid' ),
				'api_key'          => array( 'secret' ),
				'public_zero'      => array( '0' ),
				'public_structure' => array( array( 'label' => 'safe', 'access_token' => 'secret' ) ),
			)
		);

		$this->assertArrayNotHasKey( '_edit_lock', $filtered );
		$this->assertArrayNotHasKey( '_billing_email', $filtered );
		$this->assertArrayNotHasKey( 'api_key', $filtered );
		$this->assertSame( '0', $filtered['public_zero'] );
		$this->assertSame( array( 'label' => 'safe' ), $filtered['public_structure'] );
	}

	public function test_admin_mutations_require_a_valid_nonce_and_capability() {
		global $mock_nonce_valid, $mock_user_can;

		$mock_nonce_valid = false;
		$mock_user_can = true;
		$this->assertFalse( Moltex_Exporter_Security_Filters::verify_nonce( 'invalid' ) );
		$this->assertTrue( Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) );

		$mock_nonce_valid = true;
		$mock_user_can = false;
		$this->assertTrue( Moltex_Exporter_Security_Filters::verify_nonce( 'valid' ) );
		$this->assertFalse( Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) );

		unset( $mock_nonce_valid, $mock_user_can );
	}
}
