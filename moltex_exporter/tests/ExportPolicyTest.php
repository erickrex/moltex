<?php

use PHPUnit\Framework\TestCase;

class ExportPolicyTest extends TestCase {

	public function test_defaults_bundle_all_media_and_keep_personal_data_off() {
		$policy = Moltex_Exporter_Export_Policy::sanitize( array() );
		$this->assertSame( 'bundle_all', $policy['media_acquisition'] );
		$this->assertSame( Moltex_Exporter_Export_Policy::DEFAULT_PART_MAX_BYTES, $policy['part_max_bytes'] );
		$this->assertSame( array(), $policy['geodirectory_include_fields'] );
		$this->assertSame( array(), $policy['include_non_public_post_types'] );
		$this->assertFalse( $policy['include_user_emails'] );
		$this->assertFalse( $policy['include_subscribers'] );
	}

	public function test_lists_are_normalized_and_unsafe_keys_dropped() {
		$policy = Moltex_Exporter_Export_Policy::sanitize( array(
			'geodirectory_include_fields' => 'Featured, precio_por_hora  expire_date,../etc,featured',
			'include_non_public_post_types' => array( 'wp_story', 'popup_theme', '<script>' ),
			'media_acquisition' => 'featured_only',
			'part_max_bytes' => '1',
		) );
		$this->assertSame( array( 'expire_date', 'featured', 'precio_por_hora' ), $policy['geodirectory_include_fields'] );
		$this->assertSame( array( 'popup_theme', 'wp_story' ), $policy['include_non_public_post_types'] );
		$this->assertSame( 'featured_only', $policy['media_acquisition'] );
		$this->assertSame( Moltex_Exporter_Export_Policy::MIN_PART_MAX_BYTES, $policy['part_max_bytes'] );
	}

	public function test_admin_sanitizer_includes_policy_keys() {
		$admin = new Moltex_Exporter_Admin_Page();
		$sanitized = $admin->sanitize_settings( array( 'include_user_emails' => '1', 'media_acquisition' => 'bogus' ) );
		$this->assertTrue( $sanitized['include_user_emails'] );
		$this->assertSame( 'bundle_all', $sanitized['media_acquisition'] );
		$this->assertSame( 'complete', $sanitized['export_mode'] );
	}
}
