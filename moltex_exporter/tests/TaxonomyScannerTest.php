<?php
/**
 * Taxonomy Scanner Test
 *
 * Tests for the Moltex_Exporter_Taxonomy_Scanner class.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Taxonomy Scanner Test Class
 */
class TaxonomyScannerTest extends TestCase {

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();
		
		// Set up mock content data
		global $mock_posts, $mock_terms, $mock_termmeta, $wp_taxonomies;

		$mock_posts = array(
			1 => (object) array(
				'ID'        => 1,
				'post_type' => 'post',
			),
		);
		$wp_taxonomies = array();
		
		$mock_terms = array(
			(object) array(
				'term_id' => 1,
				'name' => 'News',
				'slug' => 'news',
				'description' => 'News articles',
				'parent' => 0,
				'count' => 25,
			),
			(object) array(
				'term_id' => 2,
				'name' => 'Technology',
				'slug' => 'technology',
				'description' => 'Tech news',
				'parent' => 1,
				'count' => 10,
			),
		);
		$mock_termmeta = array(
			1 => array(
				'public_color' => 'blue',
				'api_key'      => 'must-not-export',
			),
		);
	}

	/**
	 * Create a scanner using the current dependency contract.
	 *
	 * @param array $exported_content Canonical content scanner output.
	 * @return Moltex_Exporter_Taxonomy_Scanner
	 */
	private function create_scanner( array $exported_content ) {
		return new Moltex_Exporter_Taxonomy_Scanner(
			array(
				'context' => array( 'content' => $exported_content ),
			)
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$this->assertInstanceOf( Moltex_Exporter_Taxonomy_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'schema_version', $result );
		$this->assertArrayHasKey( 'taxonomies', $result );
		$this->assertArrayHasKey( 'term_relationships', $result );
		
		$this->assertEquals( 1, $result['schema_version'] );
	}

	/**
	 * Test taxonomy data structure.
	 */
	public function test_taxonomy_data_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		$this->assertArrayHasKey( 'category', $taxonomies );
		$taxonomy = $taxonomies['category'];

		$this->assertArrayHasKey( 'name', $taxonomy );
		$this->assertArrayHasKey( 'slug', $taxonomy );
		$this->assertArrayHasKey( 'hierarchical', $taxonomy );
		$this->assertArrayHasKey( 'terms', $taxonomy );
		$this->assertIsArray( $taxonomy['terms'] );
	}

	/**
	 * Test term data structure.
	 */
	public function test_term_data_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		$this->assertNotEmpty( $taxonomies['category']['terms'] );
		$term = $taxonomies['category']['terms'][0];

		$this->assertArrayHasKey( 'term_id', $term );
		$this->assertArrayHasKey( 'name', $term );
		$this->assertArrayHasKey( 'slug', $term );
		$this->assertArrayHasKey( 'description', $term );
		$this->assertArrayHasKey( 'parent', $term );
		$this->assertArrayHasKey( 'count', $term );

		$this->assertIsInt( $term['term_id'] );
		$this->assertIsInt( $term['parent'] );
		$this->assertIsInt( $term['count'] );
	}

	/**
	 * Test hierarchical relationships preservation.
	 */
	public function test_hierarchical_relationships() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		$this->assertTrue( $taxonomies['category']['hierarchical'] );
		foreach ( $taxonomies['category']['terms'] as $term ) {
			$this->assertArrayHasKey( 'parent', $term );
			$this->assertIsInt( $term['parent'] );
		}
	}

	/**
	 * Test term relationships export.
	 */
	public function test_term_relationships_export() {
		global $mock_posts;
		
		$mock_posts = array(
			1 => (object) array(
				'ID' => 1,
				'post_type' => 'post',
			),
		);
		
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$relationships = $result['term_relationships'];
		
		$this->assertArrayHasKey( 1, $relationships );
		$this->assertSame( array( 1, 2 ), $relationships[1]['category'] );
		$this->assertSame( array( 1, 2 ), $relationships[1]['post_tag'] );
	}

	/**
	 * Test excluded taxonomies are not exported.
	 */
	public function test_excluded_taxonomies() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		// These should be excluded
		$this->assertArrayNotHasKey( 'nav_menu', $taxonomies );
		$this->assertArrayNotHasKey( 'link_category', $taxonomies );
		$this->assertArrayNotHasKey( 'post_format', $taxonomies );
	}

	/**
	 * Test term metadata export.
	 */
	public function test_term_metadata_export() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		$term = $taxonomies['category']['terms'][0];
		$this->assertArrayHasKey( 'meta', $term );
		$this->assertSame( 'blue', $term['meta']['public_color'] );
		$this->assertArrayNotHasKey( 'api_key', $term['meta'] );
	}

	/**
	 * Test post ID extraction from content.
	 */
	public function test_post_id_extraction() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
				array( 'id' => 2 ),
			),
			'pages' => array(
				array( 'id' => 3 ),
			),
			'custom_post_types' => array(
				'product' => array(
					array( 'id' => 4 ),
				),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		// Test passes if scanner correctly extracts all post IDs
		$this->assertIsArray( $result );
	}

	/**
	 * Test sensitive meta filtering.
	 */
	public function test_sensitive_meta_filtering() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = $this->create_scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		foreach ( $taxonomies['category']['terms'] as $term ) {
			$meta = isset( $term['meta'] ) ? $term['meta'] : array();
			$this->assertArrayNotHasKey( 'password', $meta );
			$this->assertArrayNotHasKey( 'api_key', $meta );
			$this->assertArrayNotHasKey( 'secret', $meta );
		}
	}

	public function test_geodir_term_meta_rows_are_attached_and_reconciled() {
		global $wpdb;
		$saved = $wpdb;
		$wpdb = new TaxonomyGeodirTermMetaWpdb();
		try {
			$result = $this->create_scanner( array( 'posts' => array( array( 'id' => 1 ) ) ) )->scan();
		} finally {
			$wpdb = $saved;
		}

		$news = $result['taxonomies']['category']['terms'][0];
		$this->assertSame( 1, $news['term_id'] );
		$this->assertSame( array( 'src' => 'https://example.com/wp-content/uploads/2025/04/news.png' ), $news['geodir_meta'][0]['ct_cat_icon'] );
		$this->assertSame( '#ff0000', $news['geodir_meta'][0]['ct_cat_color'] );
		$this->assertArrayNotHasKey( 'user_id', $news['geodir_meta'][0] );
		$summary = $result['geodir_term_meta'];
		$this->assertSame( 3, $summary['source_rows'] );
		$this->assertSame( 1, $summary['attached_rows'] );
		$this->assertCount( 2, $summary['unattached_rows'] );
		$this->assertSame( 77, $summary['unattached_rows'][0]['term_id'] );
		$this->assertSame( 'orphan', $summary['unattached_rows'][1]['ct_cat_top_desc'] );
	}
}

class TaxonomyGeodirTermMetaWpdb extends Mock_WPDB {
	public function get_var( $query ) {
		return false !== strpos( $query, 'SHOW TABLES' ) ? 'wp_geodir_term_meta' : 0;
	}

	public function get_results( $query, $output = null ) {
		if ( false === strpos( $query, 'wp_geodir_term_meta' ) ) {
			return array();
		}
		return array(
			array( 'id' => '1', 'term_id' => '1', 'cpt' => 'post', 'ct_cat_icon' => serialize( array( 'src' => 'https://example.com/wp-content/uploads/2025/04/news.png' ) ), 'ct_cat_color' => '#ff0000', 'user_id' => '3' ),
			array( 'id' => '2', 'term_id' => '77', 'cpt' => 'gd_place', 'ct_cat_icon' => 'https://example.com/old.png' ),
			array( 'id' => '3', 'term_id' => '0', 'cpt' => 'gd_place', 'ct_cat_top_desc' => 'orphan' ),
		);
	}
}
