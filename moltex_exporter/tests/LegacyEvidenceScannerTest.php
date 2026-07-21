<?php
/**
 * Legacy evidence index regression tests.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class LegacyEvidenceScannerTest extends TestCase {
	use Moltex_Exporter_Temp_Directory_Trait;

	private $directory;

	protected function setUp(): void {
		$this->directory = $this->create_temp_directory( 'moltex-legacy-evidence' );
	}

	protected function tearDown(): void {
		$this->remove_temp_directory( $this->directory );
	}

	public function test_signature_registry_requires_exact_or_prefix_matches() {
		$registry = new Moltex_Exporter_Plugin_Signature_Registry();

		$this->assertSame( 'advanced-custom-fields', $registry->family_for_slug( 'advanced-custom-fields-pro' ) );
		$this->assertSame( 'geodirectory', $registry->resolve_shortcode( 'gd_map' )['source_plugin'] );
		$this->assertSame( 'unknown', $registry->resolve_shortcode( 'my_gd_map_copy' )['source_plugin'] );
		$this->assertSame( 'unknown', $registry->resolve_table( 'archive_geodir_shadow' )['source_plugin'] );
	}

	public function test_inactive_public_evidence_is_retained_without_loading_plugin_code() {
		$context = array(
			'plugins' => array(
				'plugins_list' => array(
					'plugins' => array(
						array( 'slug' => 'advanced-custom-fields-pro', 'active' => false ),
						array( 'slug' => 'geodirectory', 'active' => false ),
					),
				),
			),
			'content' => array(
				'posts' => array(),
				'pages' => array(
					array(
						'id' => 10,
						'type' => 'page',
						'slug' => 'home',
						'raw_html' => '<!-- wp:kadence/rowlayout /-->[gd_map width="100%"]',
						'postmeta' => array( 'hero_title' => 'Welcome', '_hero_title' => 'field_abc123' ),
					),
				),
				'custom_post_types' => array(),
			),
			'database' => array( 'custom_tables_manifest' => array() ),
		);
		$scanner = new Moltex_Exporter_Legacy_Evidence_Scanner(
			array( 'export_dir' => $this->directory, 'context' => $context )
		);
		$result = $scanner->scan();
		$entries = $result['index']['entries'];

		$this->assertCount( 3, $entries );
		$by_type = array();
		foreach ( $entries as $entry ) {
			$by_type[ $entry['artifact_type'] ] = $entry;
			$this->assertSame( 'referenced', $entry['relationship_status'] );
			$this->assertGreaterThan( 0, $entry['public_reference_count'] );
		}
		$this->assertSame( 'advanced-custom-fields', $by_type['postmeta_field']['source_plugin'] );
		$this->assertSame( 'inactive', $by_type['postmeta_field']['plugin_status'] );
		$this->assertSame( 'geodirectory', $by_type['shortcode']['source_plugin'] );
		$this->assertSame( 'missing', $by_type['block']['plugin_status'] );
		$this->assertSame( 'omitted', $by_type['shortcode']['payload']['status'] );
		$this->assertEmpty( $result['payloads'] );
	}

	public function test_custom_table_payload_keeps_only_publicly_reachable_rows() {
		$context = array(
			'plugins' => array(
				'plugins_list' => array(
					'plugins' => array( array( 'slug' => 'geodirectory', 'active' => false ) ),
				),
			),
			'content' => array(
				'posts' => array( array( 'id' => 10, 'type' => 'gd_place', 'slug' => 'public-place' ) ),
				'pages' => array(),
				'custom_post_types' => array(),
			),
			'database' => array(
				'custom_tables_manifest' => array(
					'wp_geodir_details' => array(
						'row_count' => 3,
						'is_sensitive' => false,
						'columns' => array(
							array( 'name' => 'id', 'key' => 'PRI' ),
							array( 'name' => 'post_id', 'key' => '' ),
							array( 'name' => 'label', 'key' => '' ),
						),
					),
				),
			),
			'plugin_table_exports' => array(
				array(
					'table_name' => 'wp_geodir_details',
					'rows' => array(
						array( 'id' => 1, 'post_id' => 10, 'label' => 'Public' ),
						array( 'id' => 2, 'post_id' => 99, 'label' => 'Private' ),
						array( 'id' => 3, 'post_id' => 0, 'label' => 'Orphan' ),
					),
				),
			),
		);
		$scanner = new Moltex_Exporter_Legacy_Evidence_Scanner(
			array( 'export_dir' => $this->directory, 'context' => $context )
		);

		$result = $scanner->scan();
		$entry = $result['index']['entries'][0];

		$this->assertSame( 'custom_table', $entry['artifact_type'] );
		$this->assertSame( 'inactive', $entry['plugin_status'] );
		$this->assertSame( 'referenced', $entry['relationship_status'] );
		$this->assertSame( 1, $entry['public_reference_count'] );
		$this->assertSame( 'included', $entry['payload']['status'] );
		$this->assertSame( 2, $entry['payload']['excluded_row_count'] );
		$this->assertCount( 1, $result['payloads'] );
		$this->assertSame(
			array( array( 'id' => 1, 'post_id' => 10, 'label' => 'Public' ) ),
			$result['payloads'][0]['data']['rows']
		);
	}

	public function test_oversized_reachable_table_is_deferred_without_a_payload() {
		$rows = array();
		for ( $index = 1; $index <= Moltex_Exporter_Legacy_Evidence_Scanner::MAX_REACHABLE_ROWS + 1; $index++ ) {
			$rows[] = array( 'id' => $index, 'post_id' => 10 );
		}
		$context = array(
			'plugins' => array( 'plugins_list' => array( 'plugins' => array( array( 'slug' => 'geodirectory', 'active' => false ) ) ) ),
			'content' => array(
				'posts' => array( array( 'id' => 10, 'type' => 'gd_place', 'slug' => 'public-place' ) ),
				'pages' => array(),
				'custom_post_types' => array(),
			),
			'database' => array(
				'custom_tables_manifest' => array(
					'wp_geodir_details' => array(
						'row_count' => count( $rows ),
						'is_sensitive' => false,
						'columns' => array(
							array( 'name' => 'id', 'key' => 'PRI' ),
							array( 'name' => 'post_id', 'key' => '' ),
						),
					),
				),
			),
			'plugin_table_exports' => array( array( 'table_name' => 'wp_geodir_details', 'rows' => $rows ) ),
		);
		$scanner = new Moltex_Exporter_Legacy_Evidence_Scanner(
			array( 'export_dir' => $this->directory, 'context' => $context )
		);

		$result = $scanner->scan();
		$entry = $result['index']['entries'][0];

		$this->assertSame( 'deferred', $entry['payload']['status'] );
		$this->assertSame( 'targeted-export', $entry['payload']['method'] );
		$this->assertNull( $entry['payload']['artifact'] );
		$this->assertEmpty( $result['payloads'] );
	}
}
