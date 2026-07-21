<?php
/**
 * Exporter public-network policy coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class PublicHttpPolicyTest extends TestCase {

	/**
	 * @dataProvider unsafe_url_provider
	 */
	public function test_private_and_invalid_destinations_are_rejected( $url ) {
		$this->expectException( InvalidArgumentException::class );
		Moltex_Exporter_Public_Http_Policy::require_public_url(
			$url,
			function () {
				return array( '93.184.216.34' );
			}
		);
	}

	public function unsafe_url_provider() {
		return array(
			'loopback'      => array( 'http://127.0.0.1/' ),
			'private'       => array( 'http://10.0.0.1/' ),
			'link-local'    => array( 'http://169.254.169.254/latest/meta-data/' ),
			'ipv6-loopback' => array( 'http://[::1]/' ),
			'mapped'        => array( 'http://[::ffff:127.0.0.1]/' ),
			'localhost'     => array( 'http://localhost/' ),
			'credentials'   => array( 'https://user:password@example.com/' ),
			'scheme'        => array( 'file:///etc/passwd' ),
		);
	}

	public function test_all_dns_results_must_be_public() {
		$this->expectException( InvalidArgumentException::class );
		Moltex_Exporter_Public_Http_Policy::require_public_url(
			'https://example.com/',
			function () {
				return array( '93.184.216.34', '192.168.1.5' );
			}
		);
	}

	public function test_public_https_destination_is_accepted() {
		$this->assertSame(
			'https://example.com/path',
			Moltex_Exporter_Public_Http_Policy::require_public_url(
				'https://example.com/path',
				function () {
					return array( '93.184.216.34' );
				}
			)
		);
	}

	public function test_scanners_use_safe_http_without_template_execution_fallback() {
		$content = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/scanners/class-content-scanner.php' );
		$theme = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/scanners/class-theme-scanner.php' );

		$this->assertStringContainsString( 'Moltex_Exporter_Public_Http_Policy::get', $content . $theme );
		$this->assertStringNotContainsString( 'sslverify', $content . $theme );
		$this->assertStringNotContainsString( 'capture_template_output', $content );
		$this->assertStringNotContainsString( 'include $template', $content );
	}
}
