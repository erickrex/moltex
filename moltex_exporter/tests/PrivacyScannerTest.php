<?php
/**
 * Final artifact privacy scan coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class PrivacyScannerTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-privacy-scan' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_clean_scan_receipt_is_checksum_bound_and_sorted() {
		mkdir( $this->directory . '/theme' );
		file_put_contents( $this->directory . '/theme/style.css', 'body { color: #123; }' );
		file_put_contents( $this->directory . '/site.json', '{"name":"Public site"}' );

		$receipt = ( new Moltex_Exporter_Privacy_Scanner( $this->directory ) )->scan();

		$this->assertSame( 'pass', $receipt['status'] );
		$this->assertSame( 2, $receipt['scanned_files'] );
		$this->assertSame( array( 'site.json', 'theme/style.css' ), array_column( $receipt['artifacts'], 'path' ) );
		$this->assertMatchesRegularExpression( '/^[a-f0-9]{64}$/', $receipt['artifacts'][0]['sha256'] );
	}

	/**
	 * @dataProvider sensitive_artifact_provider
	 */
	public function test_sensitive_artifact_classes_are_blocked_without_echoing_values( $path, $content ) {
		$directory = dirname( $this->directory . '/' . $path );
		if ( ! is_dir( $directory ) ) {
			mkdir( $directory, 0755, true );
		}
		file_put_contents( $this->directory . '/' . $path, $content );

		try {
			( new Moltex_Exporter_Privacy_Scanner( $this->directory ) )->scan();
			$this->fail( 'Expected the privacy scan to block the artifact.' );
		} catch ( Moltex_Exporter_Contract_Exception $error ) {
			$this->assertStringContainsString( $path, $error->getMessage() );
			$this->assertStringNotContainsString( 'MOLTEX-PRIVACY-CANARY-secret-value', $error->getMessage() );
		}
	}

	public function sensitive_artifact_provider() {
		$canary = 'MOLTEX-PRIVACY-CANARY-secret-value';
		return array(
			'json'       => array( 'evidence.json', '{"value":"' . $canary . '"}' ),
			'css'        => array( 'theme/style.css', '/* ' . $canary . ' */' ),
			'html'       => array( 'snapshots/page.html', '<p>' . $canary . '</p>' ),
			'svg'        => array( 'media/icon.svg', '<svg><text>' . $canary . '</text></svg>' ),
			'binary-like' => array( 'media/blob.bin', "\x00\x01" . $canary . "\x02" ),
			'private-key' => array( 'theme/key.txt', '-----BEGIN PRIVATE KEY-----' ),
		);
	}

	public function test_php_source_is_blocked_even_without_a_detected_credential() {
		mkdir( $this->directory . '/theme' );
		file_put_contents( $this->directory . '/theme/functions.php', '<?php add_action("init", "example");' );

		$this->expectException( Moltex_Exporter_Contract_Exception::class );
		$this->expectExceptionMessage( 'theme/functions.php (executable_source)' );
		( new Moltex_Exporter_Privacy_Scanner( $this->directory ) )->scan();
	}
}
