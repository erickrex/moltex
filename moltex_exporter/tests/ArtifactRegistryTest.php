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
		$this->assertContains( 'schemas/bundle.schema.json', $paths );
	}

	public function test_content_items_are_required_dynamic_artifacts() {
		$definition = ( new Moltex_Exporter_Artifact_Registry() )->get_definition( 'content/post/example.json' );

		$this->assertTrue( $definition['required'] );
		$this->assertSame( 'schemas/content-item.schema.json', $definition['schema'] );
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
