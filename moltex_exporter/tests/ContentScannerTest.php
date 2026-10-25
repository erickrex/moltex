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
		'wp_geodir_rating_category',
		'wp_geodir_post_locations',
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
			'featured'     => '1',
			'legacy_hours' => 'Mon 9-17',
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
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'TINYINT', 'field_type' => 'checkbox', 'frontend_title' => 'Featured', 'htmlvar_name' => 'featured', 'is_active' => '1', 'for_admin_use' => '1', 'show_in' => '[]', 'sort_order' => '6' ),
				array( 'post_type' => 'gd_nightclubs', 'data_type' => 'VARCHAR', 'field_type' => 'select', 'frontend_title' => 'Old style', 'htmlvar_name' => 'old_style', 'is_active' => '0', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '7', 'option_values' => 'Rock,Pop', 'extra_fields' => 'a:1:{s:4:"mode";s:4:"list";}' ),
				array( 'id' => '40', 'post_type' => 'gd_nightclubs', 'data_type' => '', 'field_type' => 'fieldset', 'frontend_title' => 'Details', 'htmlvar_name' => '', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '8' ),
				array( 'id' => '41', 'post_type' => 'gd_events', 'data_type' => 'VARCHAR', 'field_type' => 'text', 'frontend_title' => 'Venue', 'htmlvar_name' => 'venue', 'is_active' => '1', 'for_admin_use' => '0', 'show_in' => '["detail"]', 'sort_order' => '1' ),
			);
		}

		if ( false !== strpos( $query, "type = 'comment_images'" ) ) {
			return array( array( 'other_id' => '501', 'file' => '/2026/07/floor.jpg', 'title' => 'Floor', 'menu_order' => '0' ) );
		}

		if ( false !== strpos( $query, 'wp_geodir_attachments' ) && false === strpos( $query, 'GROUP BY a.type' ) ) {
			return array(
				array( 'ID' => '901', 'title' => 'Dance floor', 'caption' => 'Main room', 'file' => '2026/07/club.jpg', 'mime_type' => 'image/jpeg', 'menu_order' => '2', 'featured' => '1', 'metadata' => '' ),
			);
		}

		if ( false !== strpos( $query, 'GROUP BY a.type' ) ) {
			return array(
				array( 'type' => 'post_images', 'approved' => '1', 'post_status' => 'publish', 'total' => '40' ),
				array( 'type' => 'post_images', 'approved' => '0', 'post_status' => 'publish', 'total' => '2' ),
				array( 'type' => 'post_images', 'approved' => '1', 'post_status' => null, 'total' => '3' ),
				array( 'type' => 'comment_images', 'approved' => '1', 'post_status' => 'trash', 'total' => '1' ),
			);
		}

		if ( false !== strpos( $query, 'GROUP BY c.comment_approved' ) ) {
			return array(
				array( 'approved' => '1', 'post_status' => 'publish', 'total' => '100' ),
				array( 'approved' => '0', 'post_status' => 'publish', 'total' => '5' ),
				array( 'approved' => '1', 'post_status' => 'draft', 'total' => '3' ),
			);
		}

		if ( false !== strpos( $query, 'wp_geodir_rating_category' ) ) {
			return array( array( 'id' => '2', 'title' => 'Service', 'post_type' => 'gd_nightclubs', 'category' => '1,2', 'category_style' => '1', 'display_order' => '2' ), array( 'id' => '1', 'title' => 'Music', 'post_type' => 'gd_nightclubs', 'category' => '', 'category_style' => '1', 'display_order' => '1' ) );
		}

		if ( false !== strpos( $query, 'wp_geodir_post_locations' ) ) {
			return array( array( 'location_id' => '7', 'country' => 'Ecuador', 'region' => 'Pichincha', 'city' => 'Quito', 'country_slug' => 'ecuador', 'region_slug' => 'pichincha', 'city_slug' => 'quito', 'latitude' => '-0.18', 'longitude' => '-78.46', 'is_default' => '1' ) );
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
		$this->assertSame( 'approved', $data['reviews'][0]['approval_status'] );
		$this->assertSame( '/2026/07/floor.jpg', $data['reviews'][0]['images'][0]['file'] );
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

	public function test_geodirectory_configuration_lists_every_field_row_with_disposition() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'get_geodirectory_configuration' );
		$method->setAccessible( true );
		$config = $method->invoke( $scanner, array( 'gd_nightclubs' ) );
		$type = $config['post_types']['gd_nightclubs'];

		$by_key = array_column( $type['all_fields'], null, 'key' );
		$this->assertCount( 7, $type['all_fields'] );
		// Regression: the keyless fieldset row used to vanish from the count.
		$this->assertSame( 8, $type['field_summary']['source_rows'] );
		$this->assertSame( 1, $type['field_summary']['by_disposition']['no_htmlvar_name'] );
		$this->assertSame( 40, $type['unkeyed_rows'][0]['id'] );
		$this->assertSame( 'fieldset', $type['unkeyed_rows'][0]['field_type'] );
		$this->assertSame( 9, $config['field_reconciliation']['source_rows'] );
		$this->assertSame( array( 'gd_events' => 1, 'gd_nightclubs' => 8 ), $config['field_reconciliation']['by_post_type'] );
		$this->assertSame( array( array( 'id' => 41, 'post_type' => 'gd_events', 'htmlvar_name' => 'venue', 'reason' => 'post_type_not_exported' ) ), $config['field_reconciliation']['rows_outside_export'] );
		$this->assertSame( 'inactive', $by_key['old_style']['disposition'] );
		$this->assertFalse( $by_key['old_style']['is_active'] );
		$this->assertSame( array( 'mode' => 'list' ), $by_key['old_style']['definition']['extra_fields'] );
		$this->assertSame( 'sensitive:admin_note', $by_key['admin_notes']['disposition'] );
		$this->assertSame( 'admin_only', $by_key['featured']['disposition'] );
		$this->assertSame( 'sensitive:email', $by_key['contact_email']['disposition'] );
		$this->assertSame( 'exported', $by_key['phone']['disposition'] );
		$this->assertContains( 'featured', $config['privacy']['excluded_field_keys'] );
		$this->assertCount( 3, $type['fields'] );
	}

	public function test_geodirectory_allowlisted_admin_field_is_exported_but_email_never() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();
		update_option( 'moltex_settings', array( 'geodirectory_include_fields' => 'featured, contact_email' ) );

		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'get_geodirectory_metadata' );
		$method->setAccessible( true );
		$data = $method->invoke( $scanner, (object) array( 'ID' => 77, 'post_type' => 'gd_nightclubs' ) );

		$this->assertTrue( $data['custom_fields']['featured'] );
		$this->assertArrayNotHasKey( 'contact_email', $data['custom_fields'] );
		$this->assertTrue( $data['contact_flags']['has_email'] );
		$this->assertSame( array( 'legacy_hours' ), $data['diagnostics']['undeclared_value_columns'] );

		$config_method = new ReflectionMethod( $scanner, 'get_geodirectory_configuration' );
		$config_method->setAccessible( true );
		$config = $config_method->invoke( $scanner, array( 'gd_nightclubs' ) );
		$by_key = array_column( $config['post_types']['gd_nightclubs']['all_fields'], null, 'key' );
		$this->assertSame( 'operator_included', $by_key['featured']['disposition'] );
		$this->assertSame( 'sensitive:email', $by_key['contact_email']['disposition'] );
		$this->assertNotContains( 'featured', $config['privacy']['excluded_field_keys'] );
	}

	public function test_post_type_inventory_lists_non_public_types_and_honours_opt_in() {
		global $wp_post_types;
		get_post_types();
		$wp_post_types['wp_story'] = (object) array( 'name' => 'wp_story', 'label' => 'Stories', 'public' => false );
		$wp_post_types['popup'] = (object) array( 'name' => 'popup', 'label' => 'Popups', 'public' => false );
		update_option( 'moltex_settings', array( 'include_non_public_post_types' => 'wp_story' ) );

		$scanner = new Moltex_Exporter_Content_Scanner();
		$types = new ReflectionMethod( $scanner, 'get_custom_post_types' );
		$types->setAccessible( true );
		$this->assertContains( 'wp_story', $types->invoke( $scanner ) );
		$this->assertNotContains( 'popup', $types->invoke( $scanner ) );

		$method = new ReflectionMethod( $scanner, 'build_post_type_inventory' );
		$method->setAccessible( true );
		$inventory = $method->invoke( $scanner )['post_types'];
		$this->assertSame( 'operator_included', $inventory['wp_story']['reason'] );
		$this->assertTrue( $inventory['wp_story']['exported'] );
		$this->assertSame( 'non_public_not_opted_in', $inventory['popup']['reason'] );
		$this->assertSame( 10, $inventory['popup']['counts']['publish'] );
		$this->assertSame( 'exported', $inventory['post']['reason'] );
	}

	public function test_geodirectory_configuration_exports_criteria_locations_and_review_reconciliation() {
		global $wpdb;
		$wpdb = new ContentScannerGeoDirectoryWpdb();
		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'get_geodirectory_configuration' );
		$method->setAccessible( true );
		$config = $method->invoke( $scanner, array( 'gd_nightclubs' ) );

		$this->assertSame( 'Music', $config['rating_criteria'][0]['title'] );
		$this->assertSame( 2, $config['rating_criteria'][1]['id'] );
		$this->assertSame( 'quito', $config['locations']['locations'][0]['city_slug'] );
		$this->assertSame( array( 'exported' => 100, 'listing_draft' => 3, 'unapproved' => 5 ), $config['review_reconciliation']['by_reason'] );
		$this->assertSame( 108, $config['review_reconciliation']['source_rows'] );
		$this->assertSame( 46, $config['attachment_reconciliation']['source_rows'] );
		$this->assertSame( array( 'exported' => 40, 'listing_missing' => 3, 'unapproved' => 2 ), $config['attachment_reconciliation']['by_type']['post_images'] );
		$this->assertSame( array( 'listing_trash' => 1 ), $config['attachment_reconciliation']['by_type']['comment_images'] );
		$this->assertSame( 'price_level', $config['sort_fields_all'][0]['htmlvar_name'] );
	}

	public function test_business_hours_are_parsed_with_timezone() {
		$hours = Moltex_Exporter_Content_Scanner::parse_business_hours( '["Mo 12:00-00:00","Fr 09:00-14:00,18:00-23:30"],["UTC":"-5","Timezone":"America\\/Guayaquil"]' );
		$this->assertSame( array( array( 'open' => '12:00', 'close' => '00:00' ) ), $hours['days']['mo'] );
		$this->assertCount( 2, $hours['days']['fr'] );
		$this->assertSame( '-5', $hours['utc_offset'] );
		$this->assertSame( 'America/Guayaquil', $hours['timezone'] );
		$this->assertNull( Moltex_Exporter_Content_Scanner::parse_business_hours( 'call us' ) );
	}

	public function test_nested_postmeta_and_legacy_gallery_strings_move_to_diagnostics() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$method = new ReflectionMethod( $scanner, 'extract_nested_postmeta' );
		$method->setAccessible( true );
		$meta = array( 'keep' => 'x', '__2540' => array( 'post_images' => 'a.jpg|1||::b.jpg|2||' ), 'post_images' => 'a.jpg|1||' );
		$diagnostics = $method->invokeArgs( $scanner, array( &$meta ) );
		$this->assertSame( array( 'keep' => 'x' ), $meta );
		$this->assertSame( 2540, $diagnostics[0]['origin_post_id'] );
		$this->assertSame( array( 'post_images' ), $diagnostics[0]['meta_keys'] );
		$this->assertSame( 'post_images', $diagnostics[1]['key'] );
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
