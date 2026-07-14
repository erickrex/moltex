<?php
/**
 * Plugin Scanner Test
 *
 * Tests for the Moltex_Exporter_Plugin_Scanner class.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Plugin Scanner Test Class
 */
class PluginScannerTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	/**
	 * Test-owned export directory.
	 *
	 * @var string
	 */
	private $export_dir;

	protected function setUp(): void {
		parent::setUp();
		global $wp_post_types, $wp_taxonomies;
		$wp_post_types = array();
		$wp_taxonomies = array();
		get_post_types( array(), 'objects' );
		get_taxonomies( array(), 'objects' );
		$this->export_dir = $this->create_temp_directory( 'moltex-plugin-scanner' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->export_dir );
		parent::tearDown();
	}

	/**
	 * Create a scanner with an isolated export directory.
	 *
	 * @return Moltex_Exporter_Plugin_Scanner
	 */
	private function create_scanner() {
		return new Moltex_Exporter_Plugin_Scanner(
			array( 'export_dir' => $this->export_dir )
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$scanner = $this->create_scanner();
		$this->assertInstanceOf( Moltex_Exporter_Plugin_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'plugins_list', $result );
		$this->assertArrayHasKey( 'readme_exports', $result );
		$this->assertArrayHasKey( 'behavioral_fingerprints', $result );
		$this->assertArrayHasKey( 'custom_post_types', $result );
		$this->assertArrayHasKey( 'taxonomies', $result );
		$this->assertArrayHasKey( 'shortcodes', $result );
		$this->assertArrayHasKey( 'blocks', $result );
		$this->assertArrayHasKey( 'database_tables', $result );
	}

	/**
	 * Test plugins list collection.
	 */
	public function test_plugins_list_collection() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$plugins_list = $result['plugins_list'];
		
		$this->assertArrayHasKey( 'total_count', $plugins_list );
		$this->assertArrayHasKey( 'active_count', $plugins_list );
		$this->assertArrayHasKey( 'plugins', $plugins_list );
		
		$this->assertIsInt( $plugins_list['total_count'] );
		$this->assertIsArray( $plugins_list['plugins'] );
	}

	/**
	 * Test plugin metadata structure.
	 */
	public function test_plugin_metadata_structure() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$plugins = $result['plugins_list']['plugins'];
		
		if ( ! empty( $plugins ) ) {
			$plugin = $plugins[0];
			
			$this->assertArrayHasKey( 'file', $plugin );
			$this->assertArrayHasKey( 'slug', $plugin );
			$this->assertArrayHasKey( 'name', $plugin );
			$this->assertArrayHasKey( 'version', $plugin );
			$this->assertArrayHasKey( 'active', $plugin );
			
			$this->assertIsBool( $plugin['active'] );
		}
	}

	/**
	 * Test README exports structure.
	 */
	public function test_readme_exports_structure() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$readme_exports = $result['readme_exports'];
		
		$this->assertArrayHasKey( 'success', $readme_exports );
		$this->assertArrayHasKey( 'exported_count', $readme_exports );
		$this->assertArrayHasKey( 'readmes', $readme_exports );
		
		$this->assertIsBool( $readme_exports['success'] );
		$this->assertIsArray( $readme_exports['readmes'] );
	}

	/**
	 * Test behavioral fingerprints structure.
	 */
	public function test_behavioral_fingerprints_structure() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$fingerprints = $result['behavioral_fingerprints'];
		
		$this->assertArrayHasKey( 'success', $fingerprints );
		$this->assertArrayHasKey( 'count', $fingerprints );
		$this->assertArrayHasKey( 'path', $fingerprints );
	}

	/**
	 * Test custom post types documentation.
	 */
	public function test_custom_post_types_documentation() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$cpt = $result['custom_post_types'];
		
		$this->assertArrayHasKey( 'success', $cpt );
		$this->assertArrayHasKey( 'total_cpts', $cpt );
		$this->assertArrayHasKey( 'by_plugin', $cpt );
		
		$this->assertIsInt( $cpt['total_cpts'] );
		$this->assertIsArray( $cpt['by_plugin'] );
	}

	/**
	 * Test taxonomies documentation.
	 */
	public function test_taxonomies_documentation() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		$this->assertArrayHasKey( 'success', $taxonomies );
		$this->assertArrayHasKey( 'total_taxonomies', $taxonomies );
		$this->assertArrayHasKey( 'by_plugin', $taxonomies );
	}

	/**
	 * Test shortcodes documentation.
	 */
	public function test_shortcodes_documentation() {
		global $shortcode_tags;
		
		// Set up mock shortcodes
		$shortcode_tags = array(
			'test_shortcode' => 'test_callback',
		);
		
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$shortcodes = $result['shortcodes'];
		
		$this->assertIsArray( $shortcodes );
		$this->assertArrayHasKey( 'success', $shortcodes );
	}

	/**
	 * Test blocks documentation.
	 */
	public function test_blocks_documentation() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$blocks = $result['blocks'];
		
		$this->assertIsArray( $blocks );
		$this->assertArrayHasKey( 'success', $blocks );
	}

	/**
	 * Test database tables identification.
	 */
	public function test_database_tables_identification() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$tables = $result['database_tables'];
		
		$this->assertArrayHasKey( 'success', $tables );
		$this->assertArrayHasKey( 'total_tables', $tables );
		$this->assertArrayHasKey( 'by_plugin', $tables );
	}

	/**
	 * Test plugin slug extraction from file path.
	 */
	public function test_plugin_slug_extraction() {
		$scanner = $this->create_scanner();
		$result = $scanner->scan();

		$plugins = $result['plugins_list']['plugins'];
		
		if ( ! empty( $plugins ) ) {
			$plugin = $plugins[0];
			
			// Plugin file is 'akismet/akismet.php', slug should be 'akismet'
			$this->assertEquals( 'akismet', $plugin['slug'] );
		}
	}
}
