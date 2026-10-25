<?php
use PHPUnit\Framework\TestCase;

class SearchPlacementsTest extends TestCase {
	public function test_search_blocks_and_shortcodes_are_found_with_attributes() {
		$content = '<!-- wp:geodirectory/geodir-widget-search {"post_type":"gd_chicas","show":"main","customize_filters":"1"} /-->'
			. '<!-- wp:geodirectory/geodir-widget-listings {"post_type":"gd_chicas"} /-->'
			. '<p>[gd_search post_type="gd_nightclubs" hide_search_input=true]</p>';
		$found = Moltex_Exporter_Content_Scanner::find_search_placements( $content );

		$this->assertCount( 2, $found );
		$this->assertSame( 'geodirectory/geodir-widget-search', $found[0]['name'] );
		$this->assertSame( 'gd_chicas', $found[0]['attrs']['post_type'] );
		$this->assertSame( 'shortcode', $found[1]['kind'] );
		$this->assertSame( array( 'post_type' => 'gd_nightclubs', 'hide_search_input' => 'true' ), $found[1]['attrs'] );
	}

	public function test_no_placements_in_plain_content() {
		$this->assertSame( array(), Moltex_Exporter_Content_Scanner::find_search_placements( '<p>search the site</p>' ) );
	}
}
