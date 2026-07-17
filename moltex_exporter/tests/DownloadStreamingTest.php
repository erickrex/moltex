<?php
/**
 * Download response streaming coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class DownloadStreamingTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-download-stream' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_streaming_discards_every_preexisting_output_buffer() {
		$payload  = str_repeat( "moltex-zip-payload\n", 4096 );
		$zip_path = $this->directory . '/fixture.zip';
		file_put_contents( $zip_path, $payload );

		$fixture = MOLTEX_TESTS_DIR . '/fixtures/serve-download-child.php';
		$command = escapeshellarg( PHP_BINARY ) . ' ' . escapeshellarg( $fixture ) . ' ' . escapeshellarg( $zip_path );
		$process = proc_open(
			$command,
			array(
				0 => array( 'pipe', 'r' ),
				1 => array( 'pipe', 'w' ),
				2 => array( 'pipe', 'w' ),
			),
			$pipes
		);

		$this->assertIsResource( $process );
		fclose( $pipes[0] );
		$stdout = stream_get_contents( $pipes[1] );
		$stderr = stream_get_contents( $pipes[2] );
		fclose( $pipes[1] );
		fclose( $pipes[2] );
		$exit_code = proc_close( $process );

		$this->assertSame( 0, $exit_code, $stderr );
		$this->assertSame( $payload, $stdout );
	}
}
