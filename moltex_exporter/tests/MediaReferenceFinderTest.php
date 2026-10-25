<?php

use PHPUnit\Framework\TestCase;

class MediaReferenceFinderTest extends TestCase {

	private function values( array $hits, $kind ) {
		$out = array();
		foreach ( $hits as $hit ) {
			if ( $kind === $hit['kind'] ) {
				$out[] = $hit['value'];
			}
		}
		return $out;
	}

	public function test_video_source_and_poster_are_found_in_html() {
		$html = '<video poster="https://ex.test/wp-content/uploads/2023/01/p.jpg"><source src="https://ex.test/wp-content/uploads/2023/01/v.mp4" type="video/mp4"></video>';
		$hits = Moltex_Exporter_Media_Reference_Finder::find_in_html( $html, 'post:1' );
		$urls = $this->values( $hits, 'url' );
		$this->assertContains( 'https://ex.test/wp-content/uploads/2023/01/v.mp4', $urls );
		$this->assertContains( 'https://ex.test/wp-content/uploads/2023/01/p.jpg', $urls );
		foreach ( $hits as $hit ) {
			if ( '.mp4' === substr( $hit['value'], -4 ) ) {
				$this->assertSame( 'video', $hit['media_type'] );
			}
		}
	}

	public function test_block_attribute_ids_and_urls_are_found() {
		$html = '<!-- wp:kadence/image {"id":42,"url":"https://ex.test/wp-content/uploads/2024/02/marker.png"} /-->';
		$hits = Moltex_Exporter_Media_Reference_Finder::find_in_html( $html, 'post:7' );
		$this->assertSame( array( 42 ), $this->values( $hits, 'attachment_id' ) );
		$this->assertContains( 'https://ex.test/wp-content/uploads/2024/02/marker.png', $this->values( $hits, 'url' ) );
		$this->assertStringContainsString( 'block=kadence/image', $hits[0]['path'] );
	}

	public function test_theme_mods_custom_field_and_json_values_are_walked() {
		$value = array(
			'custom_logo' => '15',
			'header_mobile_logo' => array( 'id' => 16, 'url' => 'https://ex.test/wp-content/uploads/2024/01/m.svg' ),
			'video' => 'https://ex.test/wp-content/uploads/2023/05/clip.MP4',
			'json' => '{"poster":"2023/05/poster.webp"}',
			'title' => 'Not a URL 2023',
			'count' => 3,
		);
		$hits = Moltex_Exporter_Media_Reference_Finder::find( $value, 'theme_mod' );
		$ids = $this->values( $hits, 'attachment_id' );
		sort( $ids );
		$this->assertSame( array( 15, 16 ), $ids );
		$urls = $this->values( $hits, 'url' );
		$this->assertContains( 'https://ex.test/wp-content/uploads/2023/05/clip.MP4', $urls );
		$this->assertContains( '2023/05/poster.webp', $urls );
		$this->assertCount( 3, $urls );
	}

	public function test_non_media_values_and_zero_ids_are_ignored() {
		$hits = Moltex_Exporter_Media_Reference_Finder::find(
			array( 'id' => 0, 'link' => 'https://ex.test/about/', 'image_id' => 'abc', 'data' => 'data:image/png;base64,AAA' ),
			'option'
		);
		$this->assertSame( array(), $hits );
	}

	public function test_depth_is_bounded() {
		$value = 'https://ex.test/wp-content/uploads/2020/01/deep.jpg';
		for ( $i = 0; $i < 40; $i++ ) {
			$value = array( 'n' => $value );
		}
		$this->assertSame( array(), Moltex_Exporter_Media_Reference_Finder::find( $value, 'x' ) );
	}
}
