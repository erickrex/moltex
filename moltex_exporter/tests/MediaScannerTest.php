<?php
/**
 * Media Scanner Test
 *
 * Tests for the Moltex_Exporter_Media_Scanner class.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Media Scanner Test Class
 */
class MediaScannerTest extends TestCase {

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();

		global $mock_posts;
		$mock_posts = array();
		foreach ( array( 100, 200, 300, 400, 401, 402, 500 ) as $attachment_id ) {
			$mock_posts[ $attachment_id ] = (object) array(
				'ID'           => $attachment_id,
				'post_type'    => 'attachment',
				'post_title'   => 'Image ' . $attachment_id,
				'post_excerpt' => '',
			);
		}
	}

	/**
	 * Create a scanner using the current dependency contract.
	 *
	 * @param array $exported_content Canonical content scanner output.
	 * @return Moltex_Exporter_Media_Scanner
	 */
	private function create_scanner( array $exported_content ) {
		return new Moltex_Exporter_Media_Scanner(
			array(
				'context' => array( 'content' => $exported_content ),
			)
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$exported_content = array();
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$this->assertInstanceOf( Moltex_Exporter_Media_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$exported_content = array(
			'posts' => array(),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'media_map', $result );
		$this->assertArrayHasKey( 'total_files', $result );
		
		$this->assertIsArray( $result['media_map'] );
		$this->assertIsInt( $result['total_files'] );
	}

	/**
	 * Test featured image identification.
	 */
	public function test_featured_image_identification() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Featured image',
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertGreaterThan( 0, $result['total_files'] );
	}

	/**
	 * Test inline image identification from HTML.
	 */
	public function test_inline_image_identification() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'raw_html' => '<p><img src="https://example.com/wp-content/uploads/2024/01/image-200.jpg" alt="Test" /></p>',
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertSame( 1, $result['total_files'] );
	}

	/**
	 * Test block image identification.
	 */
	public function test_block_image_identification() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'blocks' => array(
						array(
							'name' => 'core/image',
							'attrs' => array(
								'id' => 300,
							),
							'html' => '<img src="https://example.com/wp-content/uploads/2024/01/image-300.jpg" />',
						),
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertGreaterThan( 0, $result['total_files'] );
	}

	/**
	 * Test gallery block identification.
	 */
	public function test_gallery_block_identification() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'blocks' => array(
						array(
							'name' => 'core/gallery',
							'attrs' => array(
								'ids' => array( 400, 401, 402 ),
							),
						),
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertGreaterThan( 0, $result['total_files'] );
	}

	/**
	 * Test media map structure.
	 */
	public function test_media_map_structure() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Test',
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$media_map = $result['media_map'];
		$this->assertCount( 1, $media_map );
		$entry = $media_map[0];

		$this->assertArrayHasKey( 'wp_src', $entry );
		$this->assertArrayHasKey( 'artifact', $entry );

		$this->assertIsString( $entry['wp_src'] );
		$this->assertIsString( $entry['artifact'] );
	}

	/**
	 * Test attachment metadata inclusion.
	 */
	public function test_attachment_metadata_inclusion() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Test',
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$media_map = $result['media_map'];
		$this->assertCount( 1, $media_map );
		$this->assertArrayHasKey( 'metadata', $media_map[0] );
		$this->assertSame( 100, $media_map[0]['metadata']['id'] );
	}

	/**
	 * Test CDN URL handling.
	 */
	public function test_cdn_url_handling() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'raw_html' => '<img src="https://cdn.example.com/image.jpg" />',
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertSame( 0, $result['total_files'] );
		$this->assertCount( 1, $result['media_map'] );
		$this->assertSame( 'cdn', $result['media_map'][0]['type'] );
		$this->assertSame( 'https://cdn.example.com/image.jpg', $result['media_map'][0]['wp_src'] );
	}

	/**
	 * Test srcset parsing.
	 */
	public function test_srcset_parsing() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'raw_html' => '<img src="image.jpg" srcset="https://example.com/wp-content/uploads/2024/01/image-100.jpg 1x, https://example.com/wp-content/uploads/2024/01/image-200.jpg 2x" />',
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertSame( 2, $result['total_files'] );
	}

	/**
	 * Test duplicate media handling.
	 */
	public function test_duplicate_media_handling() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Test',
					),
					'raw_html' => '<img src="https://example.com/wp-content/uploads/2024/01/image-100.jpg" />',
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		// Same image referenced twice should only be counted once
		$this->assertEquals( 1, $result['total_files'] );
	}

	/**
	 * Test relative path preservation.
	 */
	public function test_relative_path_preservation() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Test',
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$media_map = $result['media_map'];
		$this->assertCount( 1, $media_map );
		$this->assertStringContainsString( '2024/01', $media_map[0]['artifact'] );
	}

	/**
	 * Test EXIF data filtering.
	 */
	public function test_exif_data_filtering() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'featured_media' => array(
						'id' => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/image-100.jpg',
						'alt' => 'Test',
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$media_map = $result['media_map'];
		$this->assertCount( 1, $media_map );
		$this->assertArrayHasKey( 'exif', $media_map[0]['metadata'] );
		$this->assertArrayNotHasKey( 'latitude', $media_map[0]['metadata']['exif'] );
		$this->assertArrayNotHasKey( 'longitude', $media_map[0]['metadata']['exif'] );
		$this->assertArrayNotHasKey( 'gps', $media_map[0]['metadata']['exif'] );
	}

	/**
	 * Test inner blocks scanning.
	 */
	public function test_inner_blocks_scanning() {
		$exported_content = array(
			'posts' => array(
				array(
					'id' => 1,
					'blocks' => array(
						array(
							'name' => 'core/group',
							'innerBlocks' => array(
								array(
									'name' => 'core/image',
									'attrs' => array(
										'id' => 500,
									),
								),
							),
						),
					),
				),
			),
		);
		$export_dir = '/tmp/test';
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		// Should find images in nested blocks
		$this->assertGreaterThan( 0, $result['total_files'] );
	}
}
