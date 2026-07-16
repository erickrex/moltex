<?php
/**
 * Reference screenshot service coverage.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ReferenceScreenshotsTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	private $root;
	private $uploads;

	protected function setUp(): void {
		global $mock_options, $mock_upload_dir, $mock_attached_files;
		$this->root = $this->create_temp_directory( 'moltex-reference-service' );
		$this->uploads = $this->root . '/uploads';
		mkdir( $this->uploads );
		$mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] = array();
		$mock_upload_dir = array( 'basedir' => $this->uploads, 'error' => false );
		$mock_attached_files = array();
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->root );
	}

	public function test_valid_references_are_normalized_and_saved() {
		global $mock_attached_files, $mock_options;
		$source = $this->write_png( 'home.png' );
		$mock_attached_files[90] = $source;
		$result = ( new Moltex_Exporter_Reference_Screenshots() )->save(
			array(
				array( 'attachment_id' => 90, 'route' => '/', 'viewport' => 'Desktop 1440x1200', 'label' => 'Home' ),
			)
		);

		$this->assertTrue( $result['valid'] );
		$this->assertSame( 'desktop-1440x1200', $result['references'][0]['viewport'] );
		$this->assertSame( 'screenshots/desktop-1440x1200-home.png', $result['prepared'][0]['artifact'] );
		$this->assertSame( $result['references'], $mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] );
	}

	public function test_duplicate_artifact_paths_are_rejected_without_updating_option() {
		global $mock_attached_files, $mock_options;
		$mock_attached_files[90] = $this->write_png( 'one.png' );
		$mock_attached_files[91] = $this->write_png( 'two.png' );
		$result = ( new Moltex_Exporter_Reference_Screenshots() )->save(
			array(
				array( 'attachment_id' => 90, 'route' => '/', 'viewport' => 'desktop', 'label' => 'home' ),
				array( 'attachment_id' => 91, 'route' => '/about/', 'viewport' => 'desktop', 'label' => 'home' ),
			)
		);

		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'duplicate artifact path', implode( ' ', $result['errors'] ) );
		$this->assertSame( array(), $mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] );
	}

	public function test_non_png_and_more_than_ten_references_are_rejected() {
		global $mock_attached_files;
		$bad = $this->uploads . '/bad.png';
		file_put_contents( $bad, 'not an image' );
		$mock_attached_files[90] = $bad;
		$service = new Moltex_Exporter_Reference_Screenshots();
		$result = $service->validate( array( array( 'attachment_id' => 90, 'route' => '/', 'viewport' => 'desktop' ) ) );
		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'valid PNG', implode( ' ', $result['errors'] ) );

		$result = $service->validate( array_fill( 0, 11, array() ) );
		$this->assertFalse( $result['valid'] );
		$this->assertStringContainsString( 'At most 10', implode( ' ', $result['errors'] ) );
	}

	private function write_png( $name ) {
		$path = $this->uploads . '/' . $name;
		file_put_contents( $path, base64_decode( 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=' ) );
		return $path;
	}

	public function test_saving_an_empty_list_removes_all_references() {
		global $mock_options, $mock_upload_dir;
		$mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] = array( array( 'attachment_id' => 99 ) );
		$mock_upload_dir = array( 'basedir' => '/missing/uploads', 'error' => 'unavailable' );

		$result = ( new Moltex_Exporter_Reference_Screenshots() )->save( array() );

		$this->assertTrue( $result['valid'] );
		$this->assertSame( array(), $mock_options[ Moltex_Exporter_Reference_Screenshots::OPTION_NAME ] );
		$mock_upload_dir = null;
	}
}
