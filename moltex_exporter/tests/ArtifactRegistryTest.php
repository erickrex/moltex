<?php
/**
 * Artifact registry contract tests.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class ArtifactRegistryTest extends TestCase {

	public function test_required_contract_paths_are_explicit() {
		$paths = ( new Moltex_Exporter_Artifact_Registry() )->get_required_paths();

		$this->assertContains( 'bundle.json', $paths );
		$this->assertContains( 'site_blueprint.json', $paths );
		$this->assertContains( 'media/media_map.json', $paths );
		$this->assertContains( 'legacy_evidence_index.json', $paths );
		$this->assertContains( 'schemas/bundle.schema.json', $paths );
	}

	public function test_content_items_are_required_dynamic_artifacts() {
		$definition = ( new Moltex_Exporter_Artifact_Registry() )->get_definition( 'content/post/example.json' );

		$this->assertTrue( $definition['required'] );
		$this->assertSame( 'schemas/content-item.schema.json', $definition['schema'] );
	}

	public function test_geodirectory_configuration_is_bounded_optional_evidence() {
		$definition = ( new Moltex_Exporter_Artifact_Registry() )->get_definition( 'geodirectory.json' );

		$this->assertFalse( $definition['required'] );
		$this->assertSame( 'content', $definition['producer'] );
		$this->assertSame( 'schemas/geodirectory.schema.json', $definition['schema'] );
	}

	public function test_undeclared_paths_are_not_accepted_by_a_global_wildcard() {
		$registry = new Moltex_Exporter_Artifact_Registry();

		$this->assertNull( $registry->get_definition( 'unexpected/private.php' ) );
		$this->assertNull( $registry->get_definition( 'extensions/vendor/payload.php' ) );
		$this->assertSame(
			'extension',
			$registry->get_definition( 'extensions/vendor/evidence.json' )['producer']
		);
	}

	public function test_every_artifact_has_a_consumer_or_diagnostic_disposition() {
		$definitions = ( new Moltex_Exporter_Artifact_Registry() )->get_definitions();
		foreach ( $definitions as $definition ) {
			$this->assertArrayHasKey( 'consumer', $definition );
			$this->assertContains( $definition['disposition'], array( 'contract', 'capability', 'diagnostic' ) );
			if ( 'diagnostic' === $definition['disposition'] ) {
				$this->assertNull( $definition['consumer'] );
			} else {
				$this->assertNotEmpty( $definition['consumer'] );
			}
		}
	}

	public function test_capability_paths_match_the_harness_compiler_boundary() {
		$definitions = ( new Moltex_Exporter_Artifact_Registry() )->get_definitions();
		$actual = array();
		foreach ( $definitions as $definition ) {
			if ( 'capability' === $definition['disposition'] ) {
				$actual[] = $definition['path'];
			}
		}
		sort( $actual, SORT_STRING );

		$this->assertSame(
			array(
				'forms_config.json',
				'geodirectory.json',
				'integration_manifest.json',
				'plugins/plugins_fingerprint.json',
				'shortcodes_inventory.json',
				'widgets.json',
			),
			$actual
		);
	}

	/**
	 * @dataProvider unsafe_path_provider
	 */
	public function test_unsafe_paths_are_rejected( $path ) {
		$this->expectException( InvalidArgumentException::class );
		Moltex_Exporter_Artifact_Registry::normalize_relative_path( $path );
	}

	public function unsafe_path_provider() {
		return array(
			'traversal' => array( '../secret.json' ),
			'absolute'  => array( '/tmp/secret.json' ),
			'drive'     => array( 'C:/secret.json' ),
			'null'      => array( "content/post/a\0.json" ),
		);
	}
}
