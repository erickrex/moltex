<?php
/**
 * Canonical source-site identity coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class SiteIdentityTest extends TestCase {

	public function test_identity_preserves_name_domain_and_safe_workspace_slug() {
		$identity = Moltex_Exporter_Site_Identity::from_values(
			'https://Dev.WPTelescope.com/wordpress/',
			'WP Telescope'
		);

		$this->assertSame( 'WP Telescope', $identity['site_name'] );
		$this->assertSame( 'dev.wptelescope.com', $identity['domain'] );
		$this->assertSame( 'dev-wptelescope-com-wordpress', $identity['workspace_slug'] );
	}

	public function test_identity_rejects_an_origin_without_a_domain() {
		$this->expectException( InvalidArgumentException::class );
		Moltex_Exporter_Site_Identity::from_values( '/relative-only', 'Broken' );
	}
}
