<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-forms-scanner.php';

class PopupMakerExportTest extends TestCase {
	protected function setUp(): void {
		global $mock_posts, $mock_postmeta;
		$mock_posts = array(
			501 => (object) array( 'ID' => 501, 'post_type' => 'popup_theme', 'post_title' => 'Dark overlay', 'post_status' => 'publish', 'post_name' => 'dark', 'post_content' => '' ),
			502 => (object) array( 'ID' => 502, 'post_type' => 'popup', 'post_title' => 'Subscribe', 'post_status' => 'publish', 'post_name' => 'subscribe', 'post_content' => '[forminator_form id="3806"]' ),
		);
		$mock_postmeta = array(
			501 => array( 'popup_theme_settings' => array( 'overlay_background_color' => '#000000', 'overlay_background_opacity' => 60, 'close_text' => 'X' ) ),
			502 => array( 'popup_settings' => array(
				'theme_id'   => 501,
				'size'       => 'medium',
				'triggers'   => array( array( 'type' => 'auto_open', 'settings' => array( 'delay' => 5000, 'cookie_name' => array( 'pum-502' ) ) ) ),
				'cookies'    => array( array( 'event' => 'on_popup_close', 'settings' => array( 'name' => 'pum-502', 'time' => '1 month' ) ) ),
				'conditions' => array( array( array( 'target' => 'is_front_page' ) ) ),
			) ),
		);
	}

	protected function tearDown(): void {
		$GLOBALS['mock_posts'] = array();
		$GLOBALS['mock_postmeta'] = array();
	}

	public function test_popups_carry_theme_design_triggers_cookies_and_conditions() {
		$out = ( new Moltex_Exporter_Forms_Scanner() )->export_popup_maker();
		$popup = $out['popups'][0];
		$this->assertSame( 501, $popup['theme_id'] );
		$this->assertSame( 'Dark overlay', $popup['theme'] );
		$this->assertSame( 'auto_open', $popup['triggers'][0]['type'] );
		$this->assertSame( '1 month', $popup['cookies'][0]['settings']['time'] );
		$this->assertSame( 'is_front_page', $popup['conditions'][0][0]['target'] );
		$this->assertSame( 'medium', $popup['size']['size'] );
		$this->assertSame( '#000000', $out['themes'][0]['settings']['overlay_background_color'] );
	}
}
