<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-assets-scanner.php';

class KadenceCssWpdb extends Mock_WPDB {
	public $prefix = 'wp_';
	public $postmeta = 'wp_postmeta';
	public function get_results( $query, $output = null ) {
		if ( false !== strpos( $query, 'FROM wp_postmeta' ) ) {
			return array(
				array( 'post_id' => '42', 'meta_key' => '_kad_blocks_custom_css', 'meta_value' => '.kb-row-layout-id42_a{padding:10px}' ),
				array( 'post_id' => '43', 'meta_key' => '_kad_blocks_custom_css', 'meta_value' => '' ),
			);
		}
		return array();
	}
}

class KadenceCssInventoryTest extends TestCase {
	private $root;

	protected function setUp(): void {
		global $wpdb;
		$wpdb = new KadenceCssWpdb();
		$this->root = sys_get_temp_dir() . '/moltex-s4-' . uniqid();
		mkdir( $this->root . '/uploads/kadence/css', 0777, true );
		file_put_contents( $this->root . '/uploads/kadence/css/post-42.css', '.kb-a{color:red}' );
		file_put_contents( $this->root . '/uploads/kadence/global.css', ':root{}' );
	}

	protected function tearDown(): void {
		$it = new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $this->root, FilesystemIterator::SKIP_DOTS ), RecursiveIteratorIterator::CHILD_FIRST );
		foreach ( $it as $f ) {
			$f->isDir() ? rmdir( $f->getPathname() ) : unlink( $f->getPathname() );
		}
		rmdir( $this->root );
	}

	public function test_css_is_keyed_by_post_id_from_meta_and_files() {
		$scanner = new Moltex_Exporter_Assets_Scanner();
		$prop = new ReflectionProperty( $scanner, 'assets_dir' );
		$prop->setAccessible( true );
		$prop->setValue( $scanner, $this->root . '/export/assets' );

		$out = $scanner->build_kadence_css_inventory( $this->root . '/uploads' );

		$this->assertSame( array( '42' ), array_map( 'strval', array_keys( $out['posts'] ) ) );
		$this->assertSame( '.kb-row-layout-id42_a{padding:10px}', $out['posts']['42']['meta']['_kad_blocks_custom_css'] );
		$this->assertSame( 'assets/kadence-css/css/post-42.css', $out['posts']['42']['files'][0]['path'] );
		$this->assertSame( 'assets/kadence-css/global.css', $out['unkeyed_files'][0]['path'] );
		$this->assertFileExists( $this->root . '/export/assets/kadence-css/css/post-42.css' );
	}

	public function test_render_time_css_is_taken_from_saved_detail_snapshots() {
		mkdir( $this->root . '/export/snapshots', 0777, true );
		$page = '<html><head><style id="kadence-blocks-global-variables-inline-css">:root{--global-kb-font-size-md:1.25rem}</style>'
			. '<style id="theme-inline-css">body{margin:0}</style></head><body>'
			. '<style>.kb-row-layout-id77_1{padding:20px}</style><div class="kb-row-layout-id77_1"></div></body></html>';
		file_put_contents( $this->root . '/export/snapshots/club.html', $page );
		file_put_contents( $this->root . '/export/snapshots/plain.html', '<html><style>body{}</style></html>' );
		file_put_contents( $this->root . '/export/snapshots/manifest.json', json_encode( array( 'snapshots' => array(
			array( 'file' => 'snapshots/club.html', 'kind' => 'detail:gd_place', 'status' => 'saved', 'post_id' => 77 ),
			array( 'file' => 'snapshots/plain.html', 'kind' => 'detail:page', 'status' => 'saved', 'post_id' => 78 ),
			array( 'file' => null, 'kind' => 'detail:page', 'status' => 'duplicate', 'post_id' => 79 ),
		) ) ) );
		$scanner = new Moltex_Exporter_Assets_Scanner( array( 'export_dir' => $this->root . '/export' ) );

		$out = $scanner->build_kadence_css_inventory( $this->root . '/uploads' );

		$rendered = $out['posts']['77']['rendered'];
		$this->assertSame( 'assets/kadence-css/rendered/post-77.css', $rendered['path'] );
		$this->assertSame( 2, $rendered['style_blocks'] );
		$this->assertSame( array( 'kadence-blocks-global-variables-inline-css' ), $rendered['style_ids'] );
		$css = file_get_contents( $this->root . '/export/assets/kadence-css/rendered/post-77.css' );
		$this->assertStringContainsString( '.kb-row-layout-id77_1{padding:20px}', $css );
		$this->assertStringNotContainsString( 'margin:0', $css );
		$this->assertSame( hash( 'sha256', $css ), $rendered['sha256'] );
		$this->assertArrayNotHasKey( '78', $out['posts'] );
		$this->assertSame( array( 'snapshotted_posts' => 2, 'posts_with_css' => 1 ), $out['rendered_coverage'] );
	}
}
