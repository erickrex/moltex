<?php
/**
 * Scanner orchestration regression coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/class-exporter.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/class-scanner.php';

class ScannerOrchestratorTest extends TestCase {

	public function test_export_payload_includes_orchestrator_diagnostics() {
		$reflection = new ReflectionClass( 'Moltex_Exporter_Scanner' );
		$scanner    = $reflection->newInstanceWithoutConstructor();

		$results = $reflection->getProperty( 'results' );
		$results->setAccessible( true );
		$results->setValue( $scanner, array( 'content' => array( 'items' => array() ) ) );

		$errors = $reflection->getProperty( 'errors' );
		$errors->setAccessible( true );
		$errors->setValue(
			$scanner,
			array(
				array(
					'component' => 'content',
					'message'   => 'Content scanner failed.',
					'severity'  => 'error',
					'timestamp' => 1,
				),
			)
		);

		$warnings = $reflection->getProperty( 'warnings' );
		$warnings->setAccessible( true );
		$warnings->setValue(
			$scanner,
			array(
				array(
					'component' => 'media',
					'message'   => 'One media item was unavailable.',
					'severity'  => 'warning',
					'timestamp' => 2,
				),
			)
		);

		$method = $reflection->getMethod( 'prepare_export_results' );
		$method->setAccessible( true );
		$payload = $method->invoke( $scanner );

		$this->assertSame( $errors->getValue( $scanner ), $payload['errors'] );
		$this->assertSame( $warnings->getValue( $scanner ), $payload['warnings'] );
		$this->assertArrayHasKey( 'content', $payload );
	}

	public function test_resource_check_does_not_compare_total_wall_time_to_a_reset_php_limit() {
		$source = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-scanner.php' );

		$this->assertStringNotContainsString( 'Approaching execution time limit', $source );
		$this->assertStringNotContainsString( '$elapsed_time / $max_execution_time', $source );
	}

	/**
	 * A failed packaging step must not be reported as a successful scan.
	 *
	 * The validated ZIP is a required artifact. Before this regression fix the
	 * packaging failure was logged and discarded, so the admin response fell
	 * back to a generic "did not produce a validated download" message with no
	 * reason attached.
	 */
	public function test_packaging_failure_propagates_success_false_and_reason() {
		$source = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-scanner.php' );

		$packaging_branch = substr(
			$source,
			(int) strpos( $source, '$package_result = $this->package_artifacts();' )
		);
		$packaging_branch = substr( $packaging_branch, 0, (int) strpos( $packaging_branch, 'return $result;' ) );

		$this->assertStringContainsString( "\$result['success'] = false;", $packaging_branch );
		$this->assertStringContainsString( "\$result['error']", $packaging_branch );

		// The export/packaging failure must short-circuit run_scan instead of
		// continuing on to report a completed scan.
		$this->assertStringContainsString( "'error'    => \$export_error,", $source );
		$this->assertStringNotContainsString(
			"\$this->log_error( 'exporter', 'Failed to export data', 'error' );",
			$source
		);
	}

	/**
	 * The admin notice must expose the logged reason without requiring WP_DEBUG.
	 */
	public function test_admin_error_message_includes_logged_packager_reason() {
		$source = file_get_contents( MOLTEX_PLUGIN_DIR . '/includes/class-admin-page.php' );

		$this->assertStringContainsString( "' Reason (%s): %s'", $source );
		$this->assertStringContainsString( "array( 'packager', 'exporter' )", $source );
	}
}
