<?php
use PHPUnit\Framework\TestCase;

require_once dirname( __DIR__ ) . '/includes/scanners/class-forms-scanner.php';

class FormsForminatorTest extends TestCase {
	protected function tearDown(): void {
		global $mock_posts, $mock_postmeta;
		$mock_posts = array();
		$mock_postmeta = array();
	}

	public function test_forminator_definition_is_exported_without_submissions() {
		global $mock_posts, $mock_postmeta;
		$mock_posts = array( 3806 => (object) array( 'ID' => 3806, 'post_type' => 'forminator_forms', 'post_title' => 'popup', 'post_status' => 'publish' ) );
		$mock_postmeta = array( 3806 => array( 'forminator_form_meta' => serialize( array(
			'fields'        => array( array( 'element_id' => 'email-1', 'type' => 'email', 'field_label' => 'Email', 'required' => 'true', 'wrapper_id' => 'w1' ) ),
			'settings'      => array( 'formName' => 'Subscribe' ),
			'notifications' => array( array( 'email-subject' => 'New subscriber' ) ),
			'integrations'  => array( 'mailchimp' => array( 'api_key' => 'secret', 'list_id' => 'abc123', 'double_opt_in' => '1', 'fields_map' => array( 'EMAIL' => 'email-1' ) ), 'webhook' => array( 'url' => 'https://hooks.zapier.com/hooks/catch/1/xyz' ) ),
		) ) ) );

		$scanner = new Moltex_Exporter_Forms_Scanner();
		$method = new ReflectionMethod( $scanner, 'export_forminator' );
		$method->setAccessible( true );
		$forms = $method->invoke( $scanner );

		$this->assertCount( 1, $forms );
		$this->assertSame( 'Subscribe', $forms[0]['title'] );
		$this->assertSame( 'forms', $forms[0]['kind'] );
		$this->assertSame( 'email', $forms[0]['fields'][0]['type'] );
		$this->assertTrue( $forms[0]['fields'][0]['required'] );
		$this->assertSame( array( 'mailchimp', 'webhook' ), $forms[0]['integrations'] );
		// Destination details survive; credentials and webhook URLs do not.
		$mailchimp = $forms[0]['integration_settings']['mailchimp'];
		$this->assertSame( 'abc123', $mailchimp['list_id'] );
		$this->assertSame( array( 'EMAIL' => 'email-1' ), $mailchimp['fields_map'] );
		$this->assertSame( '[REDACTED]', $mailchimp['api_key'] );
		$this->assertSame( '[REDACTED]', $forms[0]['integration_settings']['webhook']['url'] );
		$this->assertStringNotContainsString( 'secret', json_encode( $forms ) );
		$this->assertStringNotContainsString( 'zapier', json_encode( $forms ) );
		$this->assertSame( 'not_exported', $forms[0]['submissions'] );
	}
}
