<?php
/**
 * Reviewed moltex-export/1 fixture builder for contract unit tests.
 *
 * @package Moltex_Exporter
 */

trait Moltex_Exporter_Contract_Fixture_Trait {

	private function write_contract_fixture( $directory, $mode = 'complete' ) {
		$writer = new Moltex_Exporter_Artifact_Writer( $directory );
		$writer->write_json(
			'site_blueprint.json',
			array(
				'exported_at' => '2026-07-14T20:00:00Z',
				'site'        => array(
					'url'                 => 'https://fixture.example',
					'home_url'            => 'https://fixture.example',
					'wp_version'          => '7.0.1',
					'permalink_structure' => '/%postname%/',
					'site_title'          => 'E2 Fixture',
					'language'            => 'en-US',
				),
				'theme'       => array( 'name' => 'fixture-theme' ),
				'plugins'     => array(),
				'content'     => array( 'posts' => 1 ),
				'taxonomies'  => array(),
				'media'       => array( 'count' => 0 ),
				'environment' => array( 'php' => '8.2' ),
			),
			'exporter'
		);
		$writer->write_json(
			'site_settings.json',
			array(
				'core'       => array( 'name' => 'E2 Fixture' ),
				'language'   => array( 'locale' => 'en_US' ),
				'reading'    => array(),
				'discussion' => array(),
				'media'      => array(),
			),
			'settings'
		);
		$writer->write_json( 'menus.json', array( 'menu_locations' => array(), 'menus' => array() ), 'menus' );
		$writer->write_json(
			'export_completeness.json',
			array(
				'complete'          => 'complete' === $mode,
				'post_types'        => array( 'post' => array( 'discovered' => 1, 'exported' => 1, 'excluded' => 0, 'failed' => 0, 'complete' => true ) ),
				'excluded_statuses' => array( 'private', 'draft' ),
			),
			'content'
		);
		$writer->write_json( 'media/media_map.json', array(), 'media' );
		$writer->write_json( 'migration_readiness.json', array( 'blockers' => array() ), 'migration_readiness' );
		$writer->write_json( 'seo_full.json', array( 'schema_version' => '1.0.0', 'pages' => array() ), 'seo_full' );
		$writer->write_json(
			'forms_config.json',
			array( 'detected_plugins' => array(), 'forms' => array(), 'forms_in_content' => array(), 'summary' => array() ),
			'forms'
		);
		$writer->write_json( 'integration_manifest.json', array( 'schema_version' => '1.0.0', 'integrations' => array() ), 'integration_manifest' );
		$writer->write_json(
			'content/post/fixture-post.json',
			array(
				'id'     => 101,
				'type'   => 'post',
				'slug'   => 'fixture-post',
				'status' => 'publish',
				'title'  => 'Fixture Post',
				'author' => array( 'display_name' => 'Fixture Author' ),
				'date_gmt' => '2026-07-14 20:00:00',
				'modified_gmt' => '2026-07-14 20:00:00',
				'taxonomies' => array(),
				'raw_html' => '<p>Fixture body.</p>',
				'legacy_permalink' => 'https://fixture.example/fixture-post/',
				'postmeta' => array(),
			),
			'content'
		);

		return $writer->finalize_bundle(
			array(
				'created_at'       => '2026-07-14T20:00:00Z',
				'exporter_version' => '1.1.0',
				'mode'             => $mode,
				'site_origin'      => 'https://fixture.example',
				'complete'     => 'complete' === $mode,
				'counts'       => array( 'post' => array( 'discovered' => 1, 'exported' => 1, 'excluded' => 0, 'failed' => 0, 'complete' => true ) ),
				'privacy'      => array(
					'private_content_included' => false,
					'excluded_statuses'        => array( 'private', 'draft' ),
					'metadata_policy'          => 'Moltex_Exporter_Security_Filters',
					'secret_scan'              => 'pass',
				),
			)
		);
	}

	private function zip_contract_fixture( $directory, $zip_path ) {
		$zip = new ZipArchive();
		if ( true !== $zip->open( $zip_path, ZipArchive::CREATE | ZipArchive::OVERWRITE ) ) {
			throw new RuntimeException( 'Unable to create contract test ZIP.' );
		}
		$iterator = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator( $directory, FilesystemIterator::SKIP_DOTS )
		);
		foreach ( $iterator as $file ) {
			if ( $file->isFile() ) {
				if ( str_replace( '\\', '/', $file->getPathname() ) === str_replace( '\\', '/', $zip_path ) ) {
					continue;
				}
				$relative = substr( str_replace( '\\', '/', $file->getPathname() ), strlen( str_replace( '\\', '/', $directory ) ) + 1 );
				$zip->addFile( $file->getPathname(), $relative );
			}
		}
		$zip->close();
	}
}
