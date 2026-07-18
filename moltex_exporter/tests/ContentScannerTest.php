<?php
/**
 * Content Scanner Test
 *
 * Tests for the Moltex_Exporter_Content_Scanner class.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

if ( ! defined( 'ARRAY_A' ) ) {
	define( 'ARRAY_A', 'ARRAY_A' );
}

/**
 * GeoDirectory database fixture with public and private source evidence.
 */
class ContentScannerGeoDirectoryWpdb extends Mock_WPDB {
	/** @var array */
	private $tables = array(
		'wp_geodir_gd_nightclubs_detail',
		'wp_geodir_custom_fields',
		'wp_geodir_attachments',
		'wp_geodir_post_review',
		'wp_geodir_custom_sort_fields',
		'wp_geodir_custom_advance_search_fields',
		'wp_geodir_tabs_layout',
	);

	public function prepare( $query, ...$args ) {
		return $query . ' ' . implode( ' ', array_map( 'strval', $args ) );
	}

	public function get_var( $query ) {
		foreach ( $this->tables as $table ) {
			if ( false !== strpos( $query, $table ) ) {
				return $table;
			}
		}
		return 0;
	}

	public function get_row( $query, $output = null ) {
		if ( false === strpos( $query, 'wp_geodir_gd_nightclubs_detail' ) ) {
			return null;
		}

		return array(
			'post_id'      => 77,
			'street'       => 'Calle Luna 4',
			'city'         => 'Madrid',
			'region'       => 'Madrid',
			'country'      => 'ES',
			'zip'          => '28004',
			'latitude'     => '40.4201',
			'longitude'    => '-3.7058',
			'phone'        => '+34 555 0100',
			'price_level'  => '3',
			'has_dj'       => '1',
			'contact_email'=> 'private@example.test',
			'admin_notes'  => 'never export this',
			'submit_ip'    => '192.0.2.10',
		);
	}

	public function get_results( $query, $output = null ) {
		if ( false !== strpos( $query, 'wp_geodir_custom_fields' ) ) {
			return array(
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'VARCHAR', 'field_type' => 'text', 'frontend_title' => 'Phone', 'htmlvar_name' => 'phone', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '1' ),
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'INT', 'field_type' => 'select', 'frontend_title' => 'Price level', 'htmlvar_name' => 'price_level', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '2' ),
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'TINYINT', 'field_type' => 'checkbox', 'frontend_title' => 'Has DJ', 'htmlvar_name' => 'has_dj', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '3' ),
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'VARCHAR', 'field_type' => 'email', 'frontend_title' => 'Email', 'htmlvar_name' => 'contact_email', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '4' ),
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'TEXT', 'field_type' => 'textarea', 'frontend_title' => 'Admin notes', 'htmlvar_name' => 'admin_notes', 'is_active' => '1', 'for_admin_use' => '1', 'show_in' => '[]', 'sort_order' => '5' ),
			);
		}

		if ( false !== strpos( $query, 'wp_geodir_attachments' ) ) {
			return array(
				array( 'ID' => '901', 'title' => 'Dance floor', 'caption' => 'Main room', 'file' => '2026/07/club.jpg', 'mime_type' => 'image/jpeg', 'menu_order' => '2', 'featured' => '1', 'metadata' => '' ),
			);
		}

		if ( false !== strpos( $query, 'wp_geodir_post_review' ) ) {
			return array(
				array( 'comment_ID' => '501', 'comment_author' => 'Public Guest', 'comment_date_gmt' => '2026-07-01 20:00:00', 'comment_content' => 'Great dance floor.', 'rating' => '4.5', 'ratings' => '{"music":5,"service":4}' ),
			);
		}

		if ( false !== strpos( $query, 'wp_geodir_custom_sort_fields' ) ) {
			return array( array( 'post_type' => 'gd_nightclubs', 'htmlvar_name' => 'price_level', 'frontend_title' => 'Price', 'data_type' => 'INT', 'field_type' => 'select', 'sort' => 'asc', 'sort_order' => '1', 'is_active' => '1', 'is_default' => '0' ) );
		}

		if ( false !== strpos( $query, 'wp_geodir_tabs_layout' ) ) {
			return array( array( 'post_type' => 'gd_nightclubs', 'sort_order' => '1', 'tab_layout' => 'post', 'tab_parent' => '0', 'tab_type' => 'standard', 'tab_level' => '0', 'tab_name' => 'Photos', 'tab_icon' => 'fas fa-camera', 'tab_key' => 'photos', 'tab_content' => '[gd_post_images]' ) );
		}

		return array();
	}
}

/**
 * Content Scanner Test Class
 */
class ContentScannerTest extends TestCase {

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();
		
		// Set up mock posts
		global $mock_posts, $mock_postmeta, $mock_options, $wp_post_types, $wp_taxonomies, $wpdb;
		$wpdb = new Mock_WPDB();
		$mock_options = array();
		$wp_post_types = array();
		$wp_taxonomies = array();
		
		$mock_posts = array(
			1 => (object) array(
				'ID' => 1,
				'post_type' => 'post',
				'post_name' => 'sample-post',
				'post_status' => 'publish',
				'post_title' => 'Sample Post',
				'post_excerpt' => 'This is a sample post',
				'post_author' => 1,
				'post_date_gmt' => '2024-01-15 10:30:00',
				'post_modified_gmt' => '2024-01-20 14:22:00',
				'post_content' => '<!-- wp:paragraph --><p>Test content</p><!-- /wp:paragraph -->',
			),
		);
		
		$mock_postmeta = array(
			1 => array(
				'_yoast_wpseo_title' => 'SEO Title',
				'custom_field' => 'value',
			),
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$this->assertInstanceOf( Moltex_Exporter_Content_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'posts', $result );
		$this->assertArrayHasKey( 'pages', $result );
		$this->assertArrayHasKey( 'custom_post_types', $result );
		$this->assertArrayHasKey( 'block_usage', $result );
		$this->assertArrayHasKey( 'export_mode', $result );
		$this->assertArrayHasKey( 'completeness', $result );
		$this->assertArrayHasKey( 'complete', $result['completeness'] );
	}

	/**
	 * Test content item structure.
	 */
	public function test_content_item_structure() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertArrayHasKey( 'type', $post );
			$this->assertArrayHasKey( 'id', $post );
			$this->assertArrayHasKey( 'slug', $post );
			$this->assertArrayHasKey( 'status', $post );
			$this->assertArrayHasKey( 'title', $post );
			$this->assertArrayHasKey( 'excerpt', $post );
			$this->assertArrayHasKey( 'author', $post );
			$this->assertArrayHasKey( 'date_gmt', $post );
			$this->assertArrayHasKey( 'modified_gmt', $post );
			$this->assertArrayHasKey( 'taxonomies', $post );
			$this->assertArrayHasKey( 'blocks', $post );
			$this->assertArrayHasKey( 'raw_html', $post );
			$this->assertArrayHasKey( 'legacy_permalink', $post );
			$this->assertArrayHasKey( 'postmeta', $post );
		}
	}

	/**
	 * Test block parsing.
	 */
	public function test_block_parsing() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertIsArray( $post['blocks'] );
			
			if ( ! empty( $post['blocks'] ) ) {
				$block = $post['blocks'][0];
				
				$this->assertArrayHasKey( 'name', $block );
				$this->assertArrayHasKey( 'attrs', $block );
				$this->assertArrayHasKey( 'html', $block );
			}
		}
	}

	/**
	 * Test block usage statistics.
	 */
	public function test_block_usage_statistics() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$block_usage = $result['block_usage'];
		
		$this->assertIsArray( $block_usage );
		
		if ( ! empty( $block_usage ) ) {
			$stat = $block_usage[0];
			
			$this->assertArrayHasKey( 'name', $stat );
			$this->assertArrayHasKey( 'count', $stat );
			$this->assertIsInt( $stat['count'] );
		}
	}

	/**
	 * Test postmeta filtering.
	 */
	public function test_postmeta_filtering() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			$postmeta = $post['postmeta'];
			
			// Should include SEO meta
			$this->assertArrayHasKey( '_yoast_wpseo_title', $postmeta );
			
			// Should not include sensitive keys (if they were present)
			$this->assertArrayNotHasKey( '_edit_lock', $postmeta );
			$this->assertArrayNotHasKey( 'password', $postmeta );
		}
	}

	/**
	 * Test query logic respects limits.
	 */
	public function test_query_respects_limits() {
		// Set custom limits
		global $mock_options;
		$mock_options['moltex_settings'] = array(
			'export_mode' => 'discovery',
			'max_posts' => 2,
			'max_pages' => 1,
		);
		
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		// The actual count depends on mock data, but structure should be correct
		$this->assertIsArray( $result['posts'] );
		$this->assertIsArray( $result['pages'] );
		$this->assertSame( 'discovery', $result['export_mode'] );
		$this->assertFalse( $result['completeness']['complete'] );
	}

	public function test_bounded_snapshot_selection_is_representative_and_capped() {
		global $mock_options;
		$mock_options['page_on_front'] = 20;
		$content = array(
			'posts' => array(),
			'pages' => array(
				array( 'id' => 20, 'type' => 'page', 'slug' => 'home', 'template' => 'front-page.php', 'raw_html' => '' ),
				array( 'id' => 21, 'type' => 'page', 'slug' => 'contact', 'template' => 'contact.php', 'raw_html' => '[forminator_form id="1"]' ),
			),
			'custom_post_types' => array(),
		);

		for ( $index = 1; $index <= 15; $index++ ) {
			$content['posts'][] = array(
				'id'       => $index,
				'type'     => 'post',
				'slug'     => 'post-' . $index,
				'template' => 'default',
				'raw_html' => '',
			);
		}
		$content['custom_post_types']['event'] = array(
			array( 'id' => 30, 'type' => 'event', 'slug' => 'event', 'template' => 'single-event.php', 'raw_html' => '' ),
		);

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method  = new ReflectionMethod( $scanner, 'select_bounded_snapshot_candidates' );
		$method->setAccessible( true );
		$selected = $method->invoke( $scanner, $content );
		$ids      = array_map(
			function ( $item ) {
				return $item['id'];
			},
			$selected
		);

		$this->assertCount( 12, $selected );
		$this->assertSame( 20, $ids[0], 'The configured front page must be selected first.' );
		$this->assertContains( 21, $ids, 'A distinct page template and form route must be represented.' );
		$this->assertContains( 30, $ids, 'Every public content type must be represented.' );
	}

	/**
	 * Test GeoDirectory CPT detection.
	 */
	public function test_geodirectory_cpt_detection() {
		// Add geodir_cpt taxonomy to mock
		global $wp_taxonomies;
		$wp_taxonomies['geodir_cpt'] = (object) array(
			'name' => 'geodir_cpt',
			'label' => 'GeoDirectory CPT',
		);
		
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		// Test passes if no errors occur
		$this->assertIsArray( $result );
	}

	public function test_geodirectory_cpt_is_detected_from_its_detail_table() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'is_geodirectory_cpt' );
		$method->setAccessible( true );

		$this->assertTrue( $method->invoke( $scanner, 'gd_nightclubs' ) );
		$this->assertFalse( $method->invoke( $scanner, 'product' ) );
	}

	public function test_geodirectory_listing_exports_only_typed_public_evidence() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'get_geodirectory_metadata' );
		$method->setAccessible( true );
		$data = $method->invoke( $scanner, (object) array( 'ID' => 77, 'post_type' => 'gd_nightclubs' ) );

		$this->assertSame( 'Madrid', $data['address']['city'] );
		$this->assertSame( 40.4201, $data['geo']['latitude'] );
		$this->assertSame( 3, $data['custom_fields']['price_level'] );
		$this->assertTrue( $data['custom_fields']['has_dj'] );
		$this->assertArrayNotHasKey( 'contact_email', $data['custom_fields'] );
		$this->assertArrayNotHasKey( 'admin_notes', $data['custom_fields'] );
		$this->assertArrayNotHasKey( 'submit_ip', $data['custom_fields'] );
		$this->assertSame( 'https://example.com/wp-content/uploads/2026/07/club.jpg', $data['media'][0]['url'] );
		$this->assertSame( 'geodirectory:901', $data['media'][0]['metadata']['id'] );
		$this->assertSame( 4.5, $data['reviews'][0]['rating'] );
		$this->assertArrayNotHasKey( 'email', $data['reviews'][0] );
		$this->assertArrayNotHasKey( 'ip', $data['reviews'][0] );
	}

	public function test_geodirectory_configuration_describes_public_rebuild_behavior() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'get_geodirectory_configuration' );
		$method->setAccessible( true );
		$config = $method->invoke( $scanner, array( 'gd_nightclubs' ) );

		$this->assertSame( 1, $config['schema_version'] );
		$this->assertSame( 'phone', $config['post_types']['gd_nightclubs']['fields'][0]['key'] );
		$this->assertCount( 3, $config['post_types']['gd_nightclubs']['fields'] );
		$this->assertSame( 'price_level', $config['post_types']['gd_nightclubs']['sort_fields'][0]['key'] );
		$this->assertSame( 'photos', $config['post_types']['gd_nightclubs']['tabs'][0]['key'] );
		$this->assertContains( 'contact_email', $config['privacy']['excluded_field_keys'] );
	}

	/**
	 * Test internal links extraction.
	 */
	public function test_internal_links_extraction() {
		global $mock_posts;
		
		$mock_posts[2] = (object) array(
			'ID' => 2,
			'post_type' => 'post',
			'post_name' => 'post-with-links',
			'post_status' => 'publish',
			'post_title' => 'Post with Links',
			'post_excerpt' => '',
			'post_author' => 1,
			'post_date_gmt' => '2024-01-15 10:30:00',
			'post_modified_gmt' => '2024-01-20 14:22:00',
			'post_content' => '<p>Check out <a href="https://example.com/about/">our about page</a></p>',
		);
		
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( count( $posts ) > 1 ) {
			$post = $posts[1];
			
			$this->assertArrayHasKey( 'internal_links', $post );
			$this->assertIsArray( $post['internal_links'] );
		}
	}

	/**
	 * Test author data structure.
	 */
	public function test_author_data_structure() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertArrayHasKey( 'author', $post );
			$this->assertArrayHasKey( 'display_name', $post['author'] );
			
			// Should NOT include email or user ID
			$this->assertArrayNotHasKey( 'email', $post['author'] );
			$this->assertArrayNotHasKey( 'user_id', $post['author'] );
		}
	}
}
