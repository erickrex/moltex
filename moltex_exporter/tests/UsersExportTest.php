<?php
use PHPUnit\Framework\TestCase;

require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-user-roles-scanner.php';

class UsersExportWpdb extends Mock_WPDB {
	public $prefix = 'wp_';
	public $posts = 'wp_posts';
	public $comments = 'wp_comments';
	public $users = 'wp_users';
	public $usermeta = 'wp_usermeta';
	public function prepare( $query, ...$args ) {
		return $query . ' ' . implode( ' ', array_map( 'strval', $args ) );
	}
	public function get_var( $query ) {
		return false !== strpos( $query, 'wp_uform_fields' ) ? 'wp_uform_fields' : null;
	}
	public function get_results( $query, $output = null ) {
		if ( false !== strpos( $query, 'FROM wp_posts' ) ) {
			return array( array( 'ID' => '3596', 'post_author' => '7', 'post_type' => 'gd_chicas' ), array( 'ID' => '3600', 'post_author' => '7', 'post_type' => 'gd_chicas' ) );
		}
		if ( false !== strpos( $query, 'FROM wp_comments' ) ) {
			return array( array( 'user_id' => '8', 'total' => '2' ) );
		}
		if ( false !== strpos( $query, 'FROM wp_usermeta' ) ) {
			return array( array( 'user_id' => '7', 'meta_value' => serialize( array( 'author' => true ) ) ) );
		}
		if ( false !== strpos( $query, 'FROM wp_users' ) ) {
			return array(
				array( 'ID' => '7', 'user_email' => 'mary@example.com', 'display_name' => 'Mary', 'user_registered' => '2022-01-01 00:00:00', 'user_pass' => 'hash' ),
				array( 'ID' => '8', 'user_email' => 'rev@example.com', 'display_name' => 'Rev', 'user_registered' => '2022-02-01 00:00:00' ),
			);
		}
		if ( false !== strpos( $query, 'FROM wp_uform_fields' ) ) {
			return array( array( 'id' => '1', 'form_type' => 'register', 'htmlvar_name' => 'first_name', 'site_title' => 'Nombre', 'field_type' => 'text', 'is_required' => '1', 'sort_order' => '2' ) );
		}
		return array();
	}
}

class UsersExportTest extends TestCase {
	protected function setUp(): void {
		global $wpdb;
		$wpdb = new UsersExportWpdb();
	}

	protected function tearDown(): void {
		update_option( 'moltex_settings', array() );
	}

	public function test_owners_and_reviewers_exported_without_email_or_password_by_default() {
		$export = ( new Moltex_Exporter_User_Roles_Scanner() )->build_users_export();
		$this->assertSame( 'not_exported', $export['emails'] );
		$this->assertSame( 7, $export['users'][0]['id'] );
		$this->assertSame( array( 'author' ), $export['users'][0]['roles'] );
		$this->assertSame( array( 'gd_chicas' => array( 3596, 3600 ) ), $export['users'][0]['owned_posts'] );
		$this->assertSame( 2, $export['users'][1]['comment_count'] );
		$json = json_encode( $export );
		$this->assertStringNotContainsString( '@example.com', $json );
		$this->assertStringNotContainsString( 'user_pass', $json );
		$this->assertSame( 'Nombre', $export['userswp']['form_fields'][0]['site_title'] );
		$this->assertSame( 1, $export['userswp']['form_fields'][0]['is_required'] );
	}

	public function test_emails_only_with_opt_in() {
		update_option( 'moltex_settings', array( 'include_user_emails' => '1' ) );
		$export = ( new Moltex_Exporter_User_Roles_Scanner() )->build_users_export();
		$this->assertSame( 'mary@example.com', $export['users'][0]['email'] );
	}
}
