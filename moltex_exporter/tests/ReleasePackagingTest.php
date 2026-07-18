<?php
/**
 * Release manifest and version consistency coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ReleasePackagingTest extends TestCase {

	public function test_all_release_version_declarations_match() {
		$entry = file_get_contents( MOLTEX_PLUGIN_DIR . '/moltex_exporter.php' );
		$readme = file_get_contents( MOLTEX_PLUGIN_DIR . '/readme.txt' );
		$exporter = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-exporter.php' );

		$this->assertMatchesRegularExpression( '/^ \* Version:\s+1\.2\.9$/m', $entry );
		$this->assertStringContainsString( "MOLTEX_EXPORTER_VERSION', '1.2.9'", $entry );
		$this->assertMatchesRegularExpression( '/^Stable tag:\s+1\.2\.9$/m', $readme );
		$this->assertMatchesRegularExpression( "/'exporter_version'\s*=>[^\n]+:\s*'1\\.2\\.9'/", $exporter );
	}

	public function test_release_manifest_requires_runtime_and_excludes_development_files() {
		$rules = json_decode( file_get_contents( MOLTEX_PLUGIN_DIR . '/release-files.json' ), true );
		$this->assertIsArray( $rules );

		foreach ( $rules['required_files'] as $required ) {
			$this->assertFileExists( MOLTEX_PLUGIN_DIR . '/' . $required );
		}

		$attributes = file_get_contents( MOLTEX_PLUGIN_DIR . '/.gitattributes' );
		foreach ( array( '/tests export-ignore', '/vendor export-ignore', '/composer.json export-ignore', '/composer.lock export-ignore', '/includes/scanners/.gitkeep export-ignore', '/includes/scanners/README.md export-ignore', '/tools/build-release.ps1 export-ignore', '/release-files.json export-ignore' ) as $rule ) {
			$this->assertStringContainsString( $rule, $attributes );
		}

		$this->assertContains( 'tests/', $rules['forbidden_prefixes'] );
		$this->assertContains( 'vendor/', $rules['forbidden_prefixes'] );
		$this->assertContains( 'includes/scanners/.gitkeep', $rules['forbidden_files'] );
		$builder = file_get_contents( MOLTEX_PLUGIN_DIR . '/tools/build-release.ps1' );
		$this->assertStringContainsString( 'normalizedTimestamp', $builder );
	}

	public function test_release_has_no_user_facing_screenshot_workflow() {
		$admin = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-admin-page.php' );
		$template = file_get_contents( MOLTEX_PLUGIN_DIR . '/templates/admin-page.php' );
		$script = file_get_contents( MOLTEX_PLUGIN_DIR . '/assets/js/admin.js' );
		$preflight = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-preflight.php' );

		$this->assertStringNotContainsString( 'moltex_save_reference_screenshots', $admin . $script );
		$this->assertStringNotContainsString( 'moltex-screenshot', $template . $script );
		$this->assertStringNotContainsString( 'Reference Screenshots', $template );
		$this->assertStringNotContainsString( 'No reviewed desktop/mobile reference screenshots', $preflight );
	}
}
