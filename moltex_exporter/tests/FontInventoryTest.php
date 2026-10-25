<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-assets-scanner.php';

class FontInventoryTest extends TestCase {
	private $root;

	protected function setUp(): void {
		$this->root = sys_get_temp_dir() . '/moltex-s2-' . uniqid();
		mkdir( $this->root . '/uploads/font-awesome/v6.7.2/webfonts', 0777, true );
		mkdir( $this->root . '/export', 0777, true );
		file_put_contents( $this->root . '/uploads/font-awesome/v6.7.2/webfonts/fa-solid-900.woff2', 'wOF2fake' );
		file_put_contents( $this->root . '/uploads/font-awesome/v6.7.2/readme.txt', 'skip me' );
		$GLOBALS['mock_theme_mods'] = array( 'base_font' => array( 'family' => 'Roboto', 'google' => true, 'variant' => array( 'regular', '700' ), 'subset' => 'latin' ) );
	}

	protected function tearDown(): void {
		$GLOBALS['mock_theme_mods'] = array();
		$it = new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $this->root, FilesystemIterator::SKIP_DOTS ), RecursiveIteratorIterator::CHILD_FIRST );
		foreach ( $it as $f ) {
			$f->isDir() ? rmdir( $f->getPathname() ) : unlink( $f->getPathname() );
		}
		rmdir( $this->root );
	}

	public function test_families_and_local_font_files_are_inventoried_and_copied() {
		$scanner = new Moltex_Exporter_Assets_Scanner();
		$prop = new ReflectionProperty( $scanner, 'assets_dir' );
		$prop->setAccessible( true );
		$prop->setValue( $scanner, $this->root . '/export/assets' );

		$fonts = $scanner->build_font_inventory( $this->root . '/uploads' );

		$this->assertSame( 'Roboto', $fonts['families'][0]['family'] );
		$this->assertSame( 'google', $fonts['families'][0]['source'] );
		$this->assertSame( array( 'regular', '700' ), $fonts['families'][0]['weights'] );
		$this->assertSame( array( 'latin' ), $fonts['families'][0]['subsets'] );
		$this->assertCount( 1, $fonts['files'] );
		$this->assertSame( 'assets/fonts/font-awesome/v6.7.2/webfonts/fa-solid-900.woff2', $fonts['files'][0]['path'] );
		$this->assertSame( hash( 'sha256', 'wOF2fake' ), $fonts['files'][0]['sha256'] );
		$this->assertFileExists( $this->root . '/export/assets/fonts/font-awesome/v6.7.2/webfonts/fa-solid-900.woff2' );
	}
}
