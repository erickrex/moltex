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
	use Moltex_Exporter_Temp_Directory_Trait;

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();

		global $mock_posts, $mock_upload_dir, $mock_attached_files, $mock_options, $mock_theme_mods;
		$mock_posts = array();
		$mock_options = array();
		$mock_theme_mods = array();
		$mock_upload_dir = null;
		$mock_attached_files = array();
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
	 * @param string $export_dir Optional export directory.
	 * @return Moltex_Exporter_Media_Scanner
	 */
	private function create_scanner( array $exported_content, $export_dir = '' ) {
		return new Moltex_Exporter_Media_Scanner(
			array(
				'export_dir' => $export_dir,
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

	public function test_geodirectory_gallery_inventory_defers_non_featured_binaries() {
		update_option( 'moltex_settings', array( 'media_acquisition' => 'featured_only' ) );
		$featured_url = 'https://example.com/wp-content/uploads/2026/07/geodirectory-featured.jpg';
		$gallery_url  = 'https://example.com/wp-content/uploads/2026/07/geodirectory-gallery.jpg';
		$external_url = 'https://images.example.net/geodirectory-gallery.jpg';
		$exported_content = array(
			'custom_post_types' => array(
				'gd_nightclubs' => array(
					array(
						'id' => 77,
						'geodirectory' => array(
							'media' => array(
								array(
									'url' => $featured_url,
									'alt' => 'Club exterior',
									'metadata' => array( 'id' => 'geodirectory:900', 'source' => 'geodirectory', 'featured' => true ),
								),
								array(
									'url' => $external_url,
									'alt' => 'Rooftop',
									'metadata' => array( 'id' => 'geodirectory:902', 'source' => 'geodirectory', 'featured' => false ),
								),
								array(
									'url' => $gallery_url,
									'alt' => 'Dance floor',
									'metadata' => array( 'id' => 'geodirectory:901', 'source' => 'geodirectory', 'featured' => false ),
								),
							),
						),
					),
				),
			),
		);

		$result = $this->create_scanner( $exported_content )->scan();

		$this->assertSame( 3, $result['total_files'] );
		$this->assertSame( 1, $result['bundled_files'] );
		$this->assertSame( 2, $result['deferred_files'] );
		$this->assertSame( $featured_url, $result['media_map'][0]['wp_src'] );
		$this->assertIsString( $result['media_map'][0]['artifact'] );
		$this->assertSame( 'bundled', $result['media_map'][0]['acquisition']['status'] );
		$this->assertSame( 'bundle', $result['media_map'][0]['acquisition']['method'] );
		$this->assertSame( $external_url, $result['media_map'][1]['wp_src'] );
		$this->assertNull( $result['media_map'][1]['artifact'] );
		$this->assertSame( 'deferred', $result['media_map'][1]['acquisition']['status'] );
		$this->assertSame( 'source-fetch', $result['media_map'][1]['acquisition']['method'] );
		$this->assertSame( 'local-only', $result['media_map'][1]['acquisition']['runtime_policy'] );
		$this->assertSame( $gallery_url, $result['media_map'][2]['wp_src'] );
		$this->assertNull( $result['media_map'][2]['artifact'] );
		$this->assertSame( 'geodirectory:901', $result['media_map'][2]['metadata']['id'] );
		$this->assertSame( 'deferred', $result['media_map'][2]['acquisition']['status'] );
	}

	public function test_geodirectory_export_copies_only_featured_binary() {
		global $mock_upload_dir;
		update_option( 'moltex_settings', array( 'media_acquisition' => 'featured_only' ) );

		$root       = $this->create_temp_directory( 'moltex-featured-geodirectory-media' );
		$uploads    = $root . '/uploads';
		$export_dir = $root . '/export';
		mkdir( $uploads . '/2026/07', 0755, true );
		mkdir( $export_dir );
		file_put_contents( $uploads . '/2026/07/featured.jpg', 'featured-payload' );
		file_put_contents( $uploads . '/2026/07/gallery.jpg', 'gallery-payload' );
		$mock_upload_dir = array(
			'basedir' => $uploads,
			'baseurl' => 'https://example.com/wp-content/uploads',
			'error'   => false,
		);
		$content = array(
			'custom_post_types' => array(
				'gd_nightclubs' => array(
					array(
						'geodirectory' => array(
							'media' => array(
								array(
									'url' => 'https://example.com/wp-content/uploads/2026/07/featured.jpg',
									'metadata' => array( 'featured' => true ),
								),
								array(
									'url' => 'https://example.com/wp-content/uploads/2026/07/gallery.jpg',
									'metadata' => array( 'featured' => false ),
								),
							),
						),
					),
				),
			),
		);

		try {
			$result = $this->create_scanner( $content, $export_dir )->scan();
			$this->assertFileExists( $export_dir . '/media/2026/07/featured.jpg' );
			$this->assertFileDoesNotExist( $export_dir . '/media/2026/07/gallery.jpg' );
			$this->assertNull( $result['media_map'][1]['artifact'] );
		} finally {
			$mock_upload_dir = null;
			$this->remove_temp_directory( $root );
		}
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

	public function test_byte_identical_media_share_one_exported_artifact() {
		global $mock_upload_dir;

		$root       = $this->create_temp_directory( 'moltex-media-deduplication' );
		$uploads    = $root . '/uploads';
		$export_dir = $root . '/export';
		mkdir( $uploads . '/2024/01', 0755, true );
		mkdir( $export_dir );
		file_put_contents( $uploads . '/2024/01/first.jpg', 'identical-media-payload' );
		file_put_contents( $uploads . '/2024/01/second.jpg', 'identical-media-payload' );

		$mock_upload_dir = array(
			'basedir' => $uploads,
			'baseurl' => 'https://example.com/wp-content/uploads',
			'error'   => false,
		);
		$content = array(
			'posts' => array(
				array(
					'id'             => 1,
					'featured_media' => array(
						'id'  => 100,
						'url' => 'https://example.com/wp-content/uploads/2024/01/first.jpg',
						'alt' => '',
					),
					'raw_html'       => '<img src="https://example.com/wp-content/uploads/2024/01/second.jpg" />',
				),
			),
		);

		try {
			$result = $this->create_scanner( $content, $export_dir )->scan();
			$this->assertCount( 2, $result['media_map'] );
			$this->assertSame( $result['media_map'][0]['artifact'], $result['media_map'][1]['artifact'] );

			$files = array_values(
				array_filter(
					iterator_to_array( new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $export_dir . '/media' ) ) ),
					function ( $item ) {
						return $item->isFile();
					}
				)
			);
			$this->assertCount( 1, $files );
		} finally {
			$mock_upload_dir = null;
			$this->remove_temp_directory( $root );
		}
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

	public function test_legacy_screenshot_option_is_not_collected() {
		global $mock_options;
		$root = $this->create_temp_directory( 'moltex-no-wordpress-screenshots' );
		$export = $root . '/export';
		mkdir( $export );
		$mock_options['moltex_reference_screenshots'] = array(
			array(
				'attachment_id' => 900,
				'route'         => '/',
				'viewport'      => 'desktop-1440x1200',
				'label'         => 'home',
			),
		);

		try {
			$scanner = new Moltex_Exporter_Media_Scanner(
				array(
					'export_dir' => $export,
					'context'    => array( 'content' => array() ),
				)
			);
			$result = $scanner->scan();

			$this->assertArrayNotHasKey( 'reference_screenshots', $result );
			$this->assertFalse( is_dir( $export . '/screenshots' ) );
		} finally {
			unset( $mock_options['moltex_reference_screenshots'] );
			$this->remove_temp_directory( $root );
		}
	}


	public function test_bundle_all_default_copies_every_gallery_binary_with_checksum() {
		global $mock_upload_dir;

		$root       = $this->create_temp_directory( 'moltex-bundle-all-geodirectory-media' );
		$uploads    = $root . '/uploads';
		$export_dir = $root . '/export';
		mkdir( $uploads . '/2026/07', 0755, true );
		mkdir( $export_dir );
		file_put_contents( $uploads . '/2026/07/featured.jpg', 'featured-payload' );
		file_put_contents( $uploads . '/2026/07/gallery.jpg', 'gallery-payload' );
		$mock_upload_dir = array( 'basedir' => $uploads, 'baseurl' => 'https://example.com/wp-content/uploads', 'error' => false );
		$content = array(
			'custom_post_types' => array(
				'gd_place' => array(
					array(
						'id' => 77,
						'type' => 'gd_place',
						'geodirectory' => array(
							'media' => array(
								array( 'url' => 'https://example.com/wp-content/uploads/2026/07/featured.jpg', 'metadata' => array( 'featured' => true, 'alt' => 'Front' ) ),
								array( 'url' => 'https://example.com/wp-content/uploads/2026/07/gallery.jpg', 'metadata' => array( 'featured' => false, 'alt' => '' ) ),
							),
						),
					),
				),
			),
		);

		try {
			$result = $this->create_scanner( $content, $export_dir )->scan();
			$this->assertSame( 2, $result['bundled_files'] );
			$this->assertSame( 0, $result['deferred_files'] );
			$this->assertFileExists( $export_dir . '/media/2026/07/gallery.jpg' );
			$gallery = $result['media_map'][1];
			$this->assertSame( hash( 'sha256', 'gallery-payload' ), $gallery['sha256'] );
			$this->assertSame( strlen( 'gallery-payload' ), $gallery['bytes'] );
			$this->assertSame( 'image', $gallery['media_type'] );
			$this->assertSame( array( array( 'source' => 'post', 'post_id' => 77, 'post_type' => 'gd_place', 'field' => 'geodirectory.media' ) ), $gallery['references'] );
			$this->assertSame( '', $gallery['metadata']['alt'] );
			$this->assertSame( 'none', $gallery['metadata']['alt_source'] );
			$this->assertSame( 'Front', $result['media_map'][0]['metadata']['alt'] );
			$this->assertSame( 'geodir_title', $result['media_map'][0]['metadata']['alt_source'] );
		} finally {
			$mock_upload_dir = null;
			$this->remove_temp_directory( $root );
		}
	}

	public function test_video_in_html_and_custom_field_is_mapped_with_back_reference() {
		$video  = 'https://example.com/wp-content/uploads/2023/05/club-tour.mp4';
		$poster = 'https://example.com/wp-content/uploads/2023/05/poster.webp';
		$content = array(
			'custom_post_types' => array(
				'gd_place' => array(
					array(
						'id' => 9,
						'type' => 'gd_place',
						'raw_html' => '<video poster="' . $poster . '"><source src="' . $video . '"></video>',
						'geodirectory' => array( 'custom_fields' => array( 'video' => $video ) ),
					),
				),
			),
		);

		$result = $this->create_scanner( $content )->scan();
		$by_src = array();
		foreach ( $result['media_map'] as $entry ) {
			$by_src[ $entry['wp_src'] ] = $entry;
		}
		$this->assertArrayHasKey( $video, $by_src );
		$this->assertArrayHasKey( $poster, $by_src );
		$this->assertSame( 'video', $by_src[ $video ]['media_type'] );
		$fields = array_column( $by_src[ $video ]['references'], 'field' );
		$this->assertContains( 'geodirectory.custom_fields.video', $fields );
		$this->assertContains( 'content', $fields );
	}

	public function test_site_logo_icon_and_theme_mod_images_are_collected() {
		global $mock_theme_mods;
		update_option( 'site_icon', 200 );
		$mock_theme_mods = array(
			'custom_logo' => 100,
			'header_mobile_logo' => array( 'url' => 'https://example.com/wp-content/uploads/2024/01/image-300.jpg' ),
			'blogname_color' => '#ffffff',
		);

		$result = $this->create_scanner( array() )->scan();
		$sources = array();
		foreach ( $result['media_map'] as $entry ) {
			foreach ( $entry['references'] as $reference ) {
				$sources[ $reference['source'] . '|' . $reference['field'] ] = $entry['wp_src'];
			}
		}
		$this->assertArrayHasKey( 'option:site_icon|site_icon', $sources );
		$this->assertArrayHasKey( 'theme_mod|custom_logo', $sources );
		$this->assertArrayHasKey( 'theme_mod|header_mobile_logo.url', $sources );
		$this->assertCount( 3, $result['media_map'] );
	}

	public function test_term_meta_category_icon_is_collected_with_term_reference() {
		$scanner = new Moltex_Exporter_Media_Scanner( array( 'export_dir' => '', 'context' => array(
			'content'    => array(),
			'taxonomies' => array( 'taxonomies' => array( 'gd_placecategory' => array( 'terms' => array(
				array( 'term_id' => 12, 'name' => 'Bars', 'slug' => 'bars', 'meta' => array( 'ct_cat_icon' => array( 'id' => 44, 'src' => 'https://example.com/wp-content/uploads/2024/01/image-44.jpg' ) ) ),
			) ) ) ),
		) ) );
		$result = $scanner->scan();
		$items = $result['media_map'];
		$found = null;
		foreach ( $items as $item ) {
			if ( isset( $item['wp_src'] ) && false !== strpos( $item['wp_src'], 'image-44.jpg' ) ) {
				$found = $item;
			}
		}
		$this->assertNotNull( $found );
		$this->assertSame( 'term:gd_placecategory:12', $found['references'][0]['source'] );
	}

	public function test_story_video_in_postmeta_only_is_collected() {
		// Regression: a wp_story with empty HTML and its video in postmeta gave zero media.
		$video = 'https://example.com/wp-content/uploads/2024/02/story.mp4';
		$content = array(
			'custom_post_types' => array(
				'wp_story' => array(
					array( 'id' => 31, 'type' => 'wp_story', 'raw_html' => '', 'postmeta' => array( 'web_stories_poster' => array( 'video' => $video ) ) ),
				),
			),
		);

		$result = $this->create_scanner( $content )->scan();

		$by_src = array_column( $result['media_map'], null, 'wp_src' );
		$this->assertArrayHasKey( $video, $by_src );
		$this->assertSame( 'video', $by_src[ $video ]['media_type'] );
		$this->assertContains( 'postmeta.web_stories_poster.video', array_column( $by_src[ $video ]['references'], 'field' ) );
	}

	public function test_marker_stored_only_in_geodir_term_meta_is_collected() {
		$marker = 'https://example.com/wp-content/uploads/2025/04/marker-bars.png';
		$orphan = 'https://example.com/wp-content/uploads/2025/04/marker-old.png';
		$scanner = new Moltex_Exporter_Media_Scanner( array( 'export_dir' => '', 'context' => array(
			'content'    => array(),
			'taxonomies' => array(
				'taxonomies'       => array( 'gd_placecategory' => array( 'terms' => array(
					array( 'term_id' => 12, 'name' => 'Bars', 'slug' => 'bars', 'geodir_meta' => array( array( 'cpt' => 'gd_place', 'ct_cat_icon' => array( 'src' => $marker ) ) ) ),
				) ) ),
				'geodir_term_meta' => array( 'source_rows' => 2, 'attached_rows' => 1, 'unattached_rows' => array( array( 'term_id' => 99, 'ct_cat_icon' => $orphan ) ) ),
			),
		) ) );

		$by_src = array_column( $scanner->scan()['media_map'], null, 'wp_src' );

		$this->assertArrayHasKey( $marker, $by_src );
		$this->assertSame( 'term:gd_placecategory:12', $by_src[ $marker ]['references'][0]['source'] );
		$this->assertArrayHasKey( $orphan, $by_src );
		$this->assertSame( 'geodir_term_meta:99', $by_src[ $orphan ]['references'][0]['source'] );
	}

	private static function box( $type, $body ) {
		return pack( 'N', 8 + strlen( $body ) ) . $type . $body;
	}

	public function test_unregistered_video_gets_container_details_and_poster_link() {
		global $mock_upload_dir;
		$uploads = sys_get_temp_dir() . '/moltex-video-' . uniqid();
		mkdir( $uploads . '/2024/03', 0777, true );
		// mvhd v0: timescale 1000, duration 12500 -> 12.5 s; tkhd v0: 1280x720.
		$mvhd = "\0\0\0\0" . pack( 'NNNN', 0, 0, 1000, 12500 ) . str_repeat( "\0", 80 );
		$tkhd = "\0\0\0\x03" . pack( 'NNNNN', 0, 0, 1, 0, 12500 ) . str_repeat( "\0", 8 + 8 + 36 ) . pack( 'NN', 1280 << 16, 720 << 16 );
		$mp4 = self::box( 'ftyp', 'isom' . pack( 'N', 512 ) . 'isomiso2' ) . self::box( 'mdat', random_bytes( 64 ) ) . self::box( 'moov', self::box( 'mvhd', $mvhd ) . self::box( 'trak', self::box( 'tkhd', $tkhd ) ) );
		file_put_contents( $uploads . '/2024/03/clip.mp4', $mp4 );
		$mock_upload_dir = array( 'basedir' => $uploads, 'baseurl' => 'https://example.com/wp-content/uploads', 'error' => false );
		$video = 'https://example.com/wp-content/uploads/2024/03/clip.mp4';
		$poster = 'https://example.com/wp-content/uploads/2024/03/clip-poster.jpg';
		try {
			$result = $this->create_scanner( array( 'pages' => array( array( 'id' => 4, 'type' => 'page', 'raw_html' => '<video poster="' . $poster . '" controls><source src="' . $video . '" type="video/mp4"></video>' ) ) ) )->scan();
		} finally {
			$mock_upload_dir = null;
			unlink( $uploads . '/2024/03/clip.mp4' );
			rmdir( $uploads . '/2024/03' );
			rmdir( $uploads . '/2024' );
			rmdir( $uploads );
		}

		$by_src = array_column( $result['media_map'], null, 'wp_src' );
		$this->assertSame( 12.5, $by_src[ $video ]['metadata']['length'] );
		$this->assertSame( 1280, $by_src[ $video ]['metadata']['width'] );
		$this->assertSame( 720, $by_src[ $video ]['metadata']['height'] );
		$this->assertSame( 'container_header', $by_src[ $video ]['metadata']['probe'] );
		$this->assertSame( $poster, $by_src[ $video ]['poster'] );
		$this->assertSame( array( $video ), $by_src[ $poster ]['poster_for'] );
	}
}
