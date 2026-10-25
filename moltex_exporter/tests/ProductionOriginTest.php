<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-site-options-scanner.php';

class ProductionOriginTest extends TestCase {
	public function test_origin_is_normalized_and_invalid_input_rejected() {
		$this->assertSame( 'https://meganoche.com', Moltex_Exporter_Export_Policy::origin( ' HTTPS://Meganoche.com/some/path?x=1 ' ) );
		$this->assertSame( 'http://localhost:8080', Moltex_Exporter_Export_Policy::origin( 'http://localhost:8080/' ) );
		$this->assertSame( '', Moltex_Exporter_Export_Policy::origin( 'javascript:alert(1)' ) );
		$this->assertSame( '', Moltex_Exporter_Export_Policy::origin( 'meganoche.com' ) );
		$this->assertSame( '', Moltex_Exporter_Export_Policy::sanitize( array() )['production_origin'] );
	}

	public function test_evidence_reports_staging_production_or_unconfirmed() {
		$unset = Moltex_Exporter_Site_Options_Scanner::production_origin_evidence( '', 'https://dev.meganoche.com/' );
		$this->assertSame( 'unconfirmed', $unset['status'] );
		$this->assertSame( 'https://dev.meganoche.com', $unset['source_origin'] );

		$staging = Moltex_Exporter_Site_Options_Scanner::production_origin_evidence( 'https://meganoche.com', 'https://dev.meganoche.com/' );
		$this->assertSame( 'source_is_staging', $staging['status'] );

		$same = Moltex_Exporter_Site_Options_Scanner::production_origin_evidence( 'https://dev.meganoche.com', 'https://dev.meganoche.com/' );
		$this->assertSame( 'source_is_production', $same['status'] );
	}
}
