<?php
use PHPUnit\Framework\TestCase;

class SnapshotRoutePlanTest extends TestCase {
	private $dir;

	protected function setUp(): void {
		$this->dir = sys_get_temp_dir() . '/moltex-s1-' . uniqid();
		mkdir( $this->dir );
	}

	protected function tearDown(): void {
		foreach ( array_merge( glob( $this->dir . '/snapshots/*' ) ?: array(), glob( $this->dir . '/*' ) ?: array() ) as $path ) {
			is_dir( $path ) ? rmdir( $path ) : unlink( $path );
		}
		rmdir( $this->dir );
	}

	private function scanner() {
		$scanner = new Moltex_Exporter_Content_Scanner();
		$prop = new ReflectionProperty( $scanner, 'export_dir' );
		$prop->setAccessible( true );
		$prop->setValue( $scanner, $this->dir );
		return $scanner;
	}

	private function call( $object, $method, array $args = array() ) {
		$m = new ReflectionMethod( $object, $method );
		$m->setAccessible( true );
		return $m->invokeArgs( $object, $args );
	}

	private function page( $canonical, $body ) {
		return '<html><head><link rel="canonical" href="' . $canonical . '"></head><body>' . $body . '</body></html>';
	}

	public function test_canonical_helpers() {
		$this->assertSame( 'https://x.test/a/', Moltex_Exporter_Content_Scanner::extract_canonical( $this->page( 'https://x.test/a/', '' ) ) );
		$this->assertNull( Moltex_Exporter_Content_Scanner::extract_canonical( '<html></html>' ) );
		$this->assertTrue( Moltex_Exporter_Content_Scanner::same_url( 'https://x.test/a/', 'http://x.test/a#top' ) );
		$this->assertFalse( Moltex_Exporter_Content_Scanner::same_url( 'https://x.test/', 'https://x.test/clubs/' ) );
	}

	public function test_guard_refuses_canonical_mismatch_and_duplicates() {
		$scanner = $this->scanner();
		$home = $this->page( 'https://x.test/', 'home' );
		$this->assertTrue( $this->call( $scanner, 'save_snapshot', array( 'home.html', 'https://x.test/', $home, 'home' ) ) );
		// A page that canonicalises to home must not be saved as "clubs".
		$this->assertFalse( $this->call( $scanner, 'save_snapshot', array( 'clubs.html', 'https://x.test/clubs/', $this->page( 'https://x.test/', 'clubs' ), 'detail:page' ) ) );
		// Identical bytes under another name are a duplicate.
		$this->assertFalse( $this->call( $scanner, 'save_snapshot', array( 'again.html', 'https://x.test/', $home, 'home' ) ) );
		$this->call( $scanner, 'write_snapshot_manifest' );

		$this->assertFileExists( $this->dir . '/snapshots/home.html' );
		$this->assertFileDoesNotExist( $this->dir . '/snapshots/clubs.html' );
		$manifest = json_decode( file_get_contents( $this->dir . '/snapshots/manifest.json' ), true );
		$this->assertSame( array( 'saved', 'canonical_mismatch', 'duplicate' ), array_column( $manifest['snapshots'], 'status' ) );
		$this->assertSame( 'snapshots/home.html', $manifest['snapshots'][2]['duplicate_of'] );
		$this->assertSame( array( 390, 768, 1440 ), $manifest['viewports_required'] );
	}

	public function test_route_plan_covers_home_search_and_404() {
		$plan = $this->scanner()->build_snapshot_route_plan( array() );
		$kinds = array_column( $plan, 'kind' );
		$this->assertSame( array( 'home', 'search', 'not_found' ), $kinds );
		$this->assertSame( 404, $plan[2]['expect_status'] );
	}

	public function test_full_scan_plans_archive_term_and_plugin_page_routes() {
		// Regression: scan() planned snapshots before the post-type inventory
		// existed and never had taxonomy terms, so only home/search/404 ran.
		global $mock_posts, $mock_terms, $mock_options, $wp_post_types;
		$wp_post_types = array();
		$mock_options = array( 'geodir_settings' => array( 'page_compare' => '7', 'listing_page' => 'not-a-page' ) );
		$mock_posts = array(
			1 => (object) array( 'ID' => 1, 'post_type' => 'post', 'post_name' => 'a', 'post_status' => 'publish', 'post_title' => 'A', 'post_excerpt' => '', 'post_author' => 1, 'post_date_gmt' => '2024-01-01 00:00:00', 'post_modified_gmt' => '2024-01-01 00:00:00', 'post_content' => '<p>a</p>' ),
			7 => (object) array( 'ID' => 7, 'post_type' => 'page', 'post_name' => 'compare', 'post_status' => 'publish', 'post_title' => 'Compare', 'post_excerpt' => '', 'post_author' => 1, 'post_date_gmt' => '2024-01-01 00:00:00', 'post_modified_gmt' => '2024-01-01 00:00:00', 'post_content' => '' ),
		);
		$mock_terms = array( (object) array( 'term_id' => 5, 'name' => 'Clubs', 'slug' => 'clubs', 'taxonomy' => 'category', 'count' => 3 ) );
		try {
			$this->scanner()->scan();
		} finally {
			$mock_terms = array();
			$mock_options = array();
		}

		$manifest = json_decode( file_get_contents( $this->dir . '/snapshots/manifest.json' ), true );
		$kinds = array_column( $manifest['snapshots'], 'kind' );
		$this->assertContains( 'post_type_archive', $kinds );
		$this->assertContains( 'term_archive', $kinds );
		$this->assertContains( 'plugin_page:geodirectory:compare', $kinds );
		$this->assertContains( 'search', $kinds );
		$this->assertContains( 'not_found', $kinds );
	}
}

if ( ! function_exists( 'get_post_type_archive_link' ) ) {
	function get_post_type_archive_link( $post_type ) {
		return 'https://example.com/' . $post_type . '/';
	}
}

if ( ! function_exists( 'get_term_link' ) ) {
	function get_term_link( $term, $taxonomy = '' ) {
		return 'https://example.com/' . $taxonomy . '/' . ( is_object( $term ) ? $term->term_id : $term ) . '/';
	}
}
