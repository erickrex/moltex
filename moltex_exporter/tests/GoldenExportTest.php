<?php
/**
 * Immutable real WordPress Golden Path export coverage.
 *
 * The reviewed oracle is checked in. This test must never regenerate it.
 *
 * @package Moltex_Exporter
 */

use PHPUnit\Framework\TestCase;

class GoldenExportTest extends TestCase {

	private $sample;
	private $expected;

	protected function setUp(): void {
		$sample_root    = dirname( MOLTEX_PLUGIN_DIR ) . '/samples';
		$this->sample  = $sample_root . '/golden-export.zip';
		$this->expected = json_decode( file_get_contents( $sample_root . '/golden-export.expected.json' ), true );

		$this->assertIsArray( $this->expected, 'Golden Export expectations must be valid JSON.' );
	}

	public function test_reviewed_archive_identity_and_contract_are_immutable() {
		$this->assertSame( $this->expected['archive_sha256'], hash_file( 'sha256', $this->sample ) );

		$result = ( new Moltex_Exporter_Bundle_Validator() )->validate_zip( $this->sample );

		$this->assertTrue( $result['valid'], implode( "\n", $result['errors'] ) );
		$this->assertTrue( $result['complete_migration_eligible'] );
		$this->assertSame( $this->expected['contract'], $result['contract'] );
		$this->assertSame( $this->expected['bundle_id'], $result['bundle_id'] );

		$zip = $this->open_sample();
		try {
			$bundle = $this->read_json( $zip, 'bundle.json' );
			$this->assertSame( $this->expected['exporter_version'], $bundle['exporter_version'] );
			$this->assertSame( $this->expected['manifest_version'], $bundle['manifest_version'] );
			$this->assertSame( $this->expected['schema_versions']['content_item'], $this->read_json( $zip, 'content/page/home.json' )['schema_version'] );
			$this->assertSame( $this->expected['schema_versions']['export_completeness'], $this->read_json( $zip, 'export_completeness.json' )['schema_version'] );
			$this->assertSame( $this->expected['schema_versions']['menus'], $this->read_json( $zip, 'menus.json' )['schema_version'] );
			$this->assertSame( $this->expected['schema_versions']['screenshots'], $this->read_json( $zip, 'screenshots/manifest.json' )['schema_version'] );
			$this->assertSame( $this->expected['schema_versions']['seo'], $this->read_json( $zip, 'seo_full.json' )['schema_version'] );
			$this->assertSame( $this->expected['schema_versions']['integrations'], $this->read_json( $zip, 'integration_manifest.json' )['schema_version'] );
		} finally {
			$zip->close();
		}
	}

	public function test_public_content_media_snapshots_and_counts_reconcile_exactly_once() {
		$zip = $this->open_sample();
		try {
			$entries = $this->entry_names( $zip );
			$content = array_values(
				array_filter(
					$entries,
					function ( $path ) {
						return 1 === preg_match( '#^content/(?:page|post)/[^/]+\.json$#', $path );
					}
				)
			);
			sort( $content );
			$this->assertSame( $this->expected['content_paths'], $content );

			$content_ids = array();
			foreach ( $content as $path ) {
				$record        = $this->read_json( $zip, $path );
				$content_ids[] = $record['id'];
				$this->assertSame( 'publish', $record['status'], $path );
			}
			sort( $content_ids );
			$this->assertSame( $this->expected['content_ids'], $content_ids );
			$this->assertCount( count( array_unique( $content_ids ) ), $content_ids );

			$media = array_values(
				array_filter(
					$entries,
					function ( $path ) {
						return 1 === preg_match( '#^media/.+\.(?:gif|jpe?g|png|svg|webp)$#i', $path );
					}
				)
			);
			sort( $media );
			$this->assertSame( $this->expected['media_paths'], $media );

			$media_map = $this->read_json( $zip, 'media/media_map.json' );
			$mapped    = array_column( $media_map, 'artifact' );
			sort( $mapped );
			$this->assertSame( $media, $mapped );
			foreach ( $media_map as $item ) {
				$this->assertNotSame( '', $item['metadata']['alt'], $item['artifact'] );
			}

			$snapshots = array_values(
				array_filter(
					$entries,
					function ( $path ) {
						return 1 === preg_match( '#^snapshots/.+\.html$#', $path );
					}
				)
			);
			$this->assertCount( $this->expected['counts']['snapshots'], $snapshots );

			$completeness = $this->read_json( $zip, 'export_completeness.json' );
			$this->assertTrue( $completeness['complete'] );
			$this->assertSame( $this->expected['counts']['pages'], $completeness['post_types']['page']['exported'] );
			$this->assertSame( $this->expected['counts']['posts'], $completeness['post_types']['post']['exported'] );
			$this->assertSame( 0, $completeness['post_types']['page']['failed'] );
			$this->assertSame( 0, $completeness['post_types']['post']['failed'] );
		} finally {
			$zip->close();
		}
	}

	public function test_reviewed_navigation_seo_capability_and_screenshots_are_preserved() {
		$zip = $this->open_sample();
		try {
			$menus = $this->read_json( $zip, 'menus.json' );
			$this->assertCount( 1, $menus['menus'] );
			$this->assertSame( $this->expected['menu']['slug'], $menus['menus'][0]['slug'] );
			$this->assertCount( $this->expected['menu']['items'], $menus['menus'][0]['items'] );
			$nested = array_values(
				array_map(
					function ( $item ) {
						return $item['object_id'];
					},
					array_filter(
						$menus['menus'][0]['items'],
						function ( $item ) {
							return '0' !== $item['parent_id'];
						}
					)
				)
			);
			sort( $nested );
			$this->assertSame( $this->expected['menu']['nested_object_ids'], $nested );

			$seo        = $this->read_json( $zip, 'seo_full.json' );
			$canonicals = array_column( $seo['pages'], 'canonical_url' );
			sort( $canonicals );
			$this->assertSame( $this->expected['seo_canonical_urls'], $canonicals );
			foreach ( $seo['pages'] as $page ) {
				$this->assertNotSame( '', $page['resolved_title'] );
				$this->assertNotSame( '', $page['meta_description'] );
			}

			$integrations = $this->read_json( $zip, 'integration_manifest.json' );
			$ids          = array_column( $integrations['integrations'], 'integration_id' );
			sort( $ids );
			$this->assertSame( $this->expected['integration_ids'], $ids );

			$manifest = $this->read_json( $zip, 'screenshots/manifest.json' );
			$this->assertCount( $this->expected['counts']['screenshots'], $manifest['screenshots'] );
			foreach ( $this->expected['screenshots'] as $index => $expected ) {
				$actual = $manifest['screenshots'][ $index ];
				$this->assertSame( $expected['artifact'], $actual['artifact'] );
				$this->assertSame( $expected['route'], $actual['route'] );
				$this->assertSame( $expected['viewport'], $actual['viewport'] );
				$this->assertSame( $expected['sha256'], $actual['sha256'] );
				$this->assertSame( $expected['sha256'], hash( 'sha256', $zip->getFromName( $actual['artifact'] ) ) );
			}
		} finally {
			$zip->close();
		}
	}

	public function test_private_fixture_markers_are_absent_from_shareable_evidence() {
		$zip = $this->open_sample();
		try {
			foreach ( $this->entry_names( $zip ) as $path ) {
				if ( 1 !== preg_match( '#\.(?:css|csv|html|js|json|sql|txt)$#', $path ) ) {
					continue;
				}
				$content = $zip->getFromName( $path );
				foreach ( $this->expected['private_markers'] as $marker ) {
					$this->assertStringNotContainsString( $marker, $content, $path );
				}
			}
		} finally {
			$zip->close();
		}
	}

	private function open_sample() {
		$zip = new ZipArchive();
		$this->assertTrue( true === $zip->open( $this->sample ), 'Could not open Golden Export ZIP.' );
		return $zip;
	}

	private function entry_names( ZipArchive $zip ) {
		$entries = array();
		for ( $index = 0; $index < $zip->numFiles; $index++ ) {
			$path = $zip->getNameIndex( $index );
			if ( '/' !== substr( $path, -1 ) ) {
				$entries[] = $path;
			}
		}
		return $entries;
	}

	private function read_json( ZipArchive $zip, $path ) {
		$content = $zip->getFromName( $path );
		$this->assertNotFalse( $content, 'Missing Golden Export artifact: ' . $path );
		$data = json_decode( $content, true );
		$this->assertIsArray( $data, 'Invalid Golden Export JSON: ' . $path );
		return $data;
	}
}
