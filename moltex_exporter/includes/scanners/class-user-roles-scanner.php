<?php
/**
 * User Roles Scanner
 *
 * Exports user roles and capabilities without exporting actual user accounts.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Moltex_Exporter_User_Roles_Scanner
 *
 * Collects user roles and capabilities data.
 */
class Moltex_Exporter_User_Roles_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Default WordPress roles
	 *
	 * @var array
	 */
	private $default_roles = array(
		'administrator',
		'editor',
		'author',
		'contributor',
		'subscriber',
	);

	/**
	 * Known role management plugins
	 *
	 * @var array
	 */
	private $role_plugins = array(
		'members/members.php'                              => 'Members',
		'user-role-editor/user-role-editor.php'            => 'User Role Editor',
		'capability-manager-enhanced/capsman-enhanced.php' => 'Capability Manager Enhanced',
		'advanced-access-manager/aam.php'                  => 'Advanced Access Manager',
		'user-role-editor-pro/user-role-editor-pro.php'    => 'User Role Editor Pro',
	);

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan user roles and capabilities
	 *
	 * @return array User roles data
	 */
	public function scan() {
		global $wp_roles;

		if ( ! isset( $wp_roles ) ) {
			$wp_roles = new WP_Roles();
		}

		$data = array(
			'schema_version'          => 1,
			'roles'                   => array(),
			'custom_roles'            => array(),
			'modified_default_roles'  => array(),
			'role_management_plugins' => array(),
			'total_roles'             => 0,
			'scan_timestamp'          => current_time( 'mysql' ),
		);

		$data['users_export'] = $this->build_users_export();

		// Get all roles
		$roles = $wp_roles->roles;
		$data['total_roles'] = count( $roles );

		// Detect role management plugins
		$data['role_management_plugins'] = $this->detect_role_plugins();

		// Process each role
		foreach ( $roles as $role_slug => $role_data ) {
			$role_info = array(
				'slug'             => $role_slug,
				'name'             => $role_data['name'],
				'capabilities'     => $role_data['capabilities'],
				'is_default'       => in_array( $role_slug, $this->default_roles, true ),
				'is_custom'        => ! in_array( $role_slug, $this->default_roles, true ),
				'capability_count' => count( $role_data['capabilities'] ),
			);

			// Add to roles array
			$data['roles'][ $role_slug ] = $role_info;

			// Track custom roles
			if ( $role_info['is_custom'] ) {
				$data['custom_roles'][] = $role_slug;
			}

			// Check if default role has been modified
			if ( $role_info['is_default'] ) {
				$modifications = $this->detect_role_modifications( $role_slug, $role_data['capabilities'] );
				if ( ! empty( $modifications ) ) {
					$data['modified_default_roles'][ $role_slug ] = $modifications;
				}
			}
		}

		return $data;
	}

	/**
	 * Detect installed role management plugins
	 *
	 * @return array List of detected role management plugins
	 */
	private function detect_role_plugins() {
		$detected = array();

		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$active_plugins = get_option( 'active_plugins', array() );

		foreach ( $this->role_plugins as $plugin_file => $plugin_name ) {
			if ( in_array( $plugin_file, $active_plugins, true ) ) {
				$detected[] = array(
					'name'   => $plugin_name,
					'file'   => $plugin_file,
					'active' => true,
				);
			} else {
				// Check if plugin exists but is inactive
				$all_plugins = get_plugins();
				if ( isset( $all_plugins[ $plugin_file ] ) ) {
					$detected[] = array(
						'name'   => $plugin_name,
						'file'   => $plugin_file,
						'active' => false,
					);
				}
			}
		}

		return $detected;
	}

	/**
	 * Detect modifications to default WordPress roles
	 *
	 * @param string $role_slug    Role slug.
	 * @param array  $current_caps Current capabilities.
	 * @return array Modifications detected.
	 */
	private function detect_role_modifications( $role_slug, $current_caps ) {
		$default_caps = $this->get_default_capabilities( $role_slug );

		if ( empty( $default_caps ) ) {
			return array();
		}

		$modifications = array(
			'added_capabilities'    => array(),
			'removed_capabilities'  => array(),
			'modified_capabilities' => array(),
		);

		// Find added capabilities
		foreach ( $current_caps as $cap => $granted ) {
			if ( ! isset( $default_caps[ $cap ] ) ) {
				$modifications['added_capabilities'][] = $cap;
			} elseif ( $default_caps[ $cap ] !== $granted ) {
				$modifications['modified_capabilities'][] = array(
					'capability'    => $cap,
					'default_value' => $default_caps[ $cap ],
					'current_value' => $granted,
				);
			}
		}

		// Find removed capabilities
		foreach ( $default_caps as $cap => $granted ) {
			if ( ! isset( $current_caps[ $cap ] ) ) {
				$modifications['removed_capabilities'][] = $cap;
			}
		}

		// Only return if there are actual modifications
		if ( empty( $modifications['added_capabilities'] ) &&
			empty( $modifications['removed_capabilities'] ) &&
			empty( $modifications['modified_capabilities'] ) ) {
			return array();
		}

		return $modifications;
	}

	/**
	 * Get default capabilities for WordPress roles
	 *
	 * @param string $role_slug Role slug.
	 * @return array Default capabilities.
	 */
	private function get_default_capabilities( $role_slug ) {
		$defaults = array(
			'administrator' => array(
				'switch_themes'          => true,
				'edit_themes'            => true,
				'activate_plugins'       => true,
				'edit_plugins'           => true,
				'edit_users'             => true,
				'edit_files'             => true,
				'manage_options'         => true,
				'moderate_comments'      => true,
				'manage_categories'      => true,
				'manage_links'           => true,
				'upload_files'           => true,
				'import'                 => true,
				'unfiltered_html'        => true,
				'edit_posts'             => true,
				'edit_others_posts'      => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'edit_pages'             => true,
				'read'                   => true,
				'level_10'               => true,
				'level_9'                => true,
				'level_8'                => true,
				'level_7'                => true,
				'level_6'                => true,
				'level_5'                => true,
				'level_4'                => true,
				'level_3'                => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'edit_others_pages'      => true,
				'edit_published_pages'   => true,
				'publish_pages'          => true,
				'delete_pages'           => true,
				'delete_others_pages'    => true,
				'delete_published_pages' => true,
				'delete_posts'           => true,
				'delete_others_posts'    => true,
				'delete_published_posts' => true,
				'delete_private_posts'   => true,
				'edit_private_posts'     => true,
				'read_private_posts'     => true,
				'delete_private_pages'   => true,
				'edit_private_pages'     => true,
				'read_private_pages'     => true,
				'delete_users'           => true,
				'create_users'           => true,
				'unfiltered_upload'      => true,
				'edit_dashboard'         => true,
				'update_plugins'         => true,
				'delete_plugins'         => true,
				'install_plugins'        => true,
				'update_themes'          => true,
				'install_themes'         => true,
				'update_core'            => true,
				'list_users'             => true,
				'remove_users'           => true,
				'promote_users'          => true,
				'edit_theme_options'     => true,
				'delete_themes'          => true,
				'export'                 => true,
			),
			'editor' => array(
				'moderate_comments'      => true,
				'manage_categories'      => true,
				'manage_links'           => true,
				'upload_files'           => true,
				'unfiltered_html'        => true,
				'edit_posts'             => true,
				'edit_others_posts'      => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'edit_pages'             => true,
				'read'                   => true,
				'level_7'                => true,
				'level_6'                => true,
				'level_5'                => true,
				'level_4'                => true,
				'level_3'                => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'edit_others_pages'      => true,
				'edit_published_pages'   => true,
				'publish_pages'          => true,
				'delete_pages'           => true,
				'delete_others_pages'    => true,
				'delete_published_pages' => true,
				'delete_posts'           => true,
				'delete_others_posts'    => true,
				'delete_published_posts' => true,
				'delete_private_posts'   => true,
				'edit_private_posts'     => true,
				'read_private_posts'     => true,
				'delete_private_pages'   => true,
				'edit_private_pages'     => true,
				'read_private_pages'     => true,
			),
			'author' => array(
				'upload_files'           => true,
				'edit_posts'             => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'read'                   => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'delete_posts'           => true,
				'delete_published_posts' => true,
			),
			'contributor' => array(
				'edit_posts'   => true,
				'read'         => true,
				'level_1'      => true,
				'level_0'      => true,
				'delete_posts' => true,
			),
			'subscriber' => array(
				'read'    => true,
				'level_0' => true,
			),
		);

		return isset( $defaults[ $role_slug ] ) ? $defaults[ $role_slug ] : array();
	}

	/**
	 * Users who own content or reviews, plus UsersWP form config (U1, U2).
	 *
	 * Never passwords, activation keys or sessions. Email only with the
	 * include_user_emails opt-in.
	 *
	 * @return array
	 */
	public function build_users_export() {
		global $wpdb;
		$owned = array();
		$skip = "'revision','nav_menu_item','attachment','customize_changeset','oembed_cache','custom_css','wp_global_styles','user_request'";
		foreach ( (array) $wpdb->get_results( "SELECT ID, post_author, post_type FROM {$wpdb->posts} WHERE post_author > 0 AND post_status IN ('publish','private','pending','draft','future') AND post_type NOT IN ({$skip}) ORDER BY ID ASC", ARRAY_A ) as $row ) {
			$owned[ (int) $row['post_author'] ][ (string) $row['post_type'] ][] = (int) $row['ID'];
		}
		$reviews = array();
		foreach ( (array) $wpdb->get_results( "SELECT user_id, COUNT(*) AS total FROM {$wpdb->comments} WHERE user_id > 0 GROUP BY user_id", ARRAY_A ) as $row ) {
			$reviews[ (int) $row['user_id'] ] = (int) $row['total'];
		}
		$ids = array_unique( array_merge( array_keys( $owned ), array_keys( $reviews ) ) );
		sort( $ids );
		$with_email = (bool) Moltex_Exporter_Export_Policy::get( 'include_user_emails' );
		$users = array();
		if ( ! empty( $ids ) ) {
			$in = implode( ',', array_map( 'intval', $ids ) );
			$cap_key = $wpdb->prefix . 'capabilities';
			$caps = array();
			foreach ( (array) $wpdb->get_results( $wpdb->prepare( "SELECT user_id, meta_value FROM {$wpdb->usermeta} WHERE meta_key = %s AND user_id IN ({$in})", $cap_key ), ARRAY_A ) as $row ) {
				$value = maybe_unserialize( $row['meta_value'] );
				$caps[ (int) $row['user_id'] ] = is_array( $value ) ? array_values( array_keys( array_filter( $value ) ) ) : array();
			}
			foreach ( (array) $wpdb->get_results( "SELECT ID, user_email, display_name, user_registered FROM {$wpdb->users} WHERE ID IN ({$in}) ORDER BY ID ASC", ARRAY_A ) as $row ) {
				$id = (int) $row['ID'];
				$user = array(
					'id'            => $id,
					'display_name'  => (string) $row['display_name'],
					'roles'         => isset( $caps[ $id ] ) ? $caps[ $id ] : array(),
					'registered'    => (string) $row['user_registered'],
					'owned_posts'   => isset( $owned[ $id ] ) ? $owned[ $id ] : array(),
					'comment_count' => isset( $reviews[ $id ] ) ? $reviews[ $id ] : 0,
				);
				if ( $with_email ) {
					$user['email'] = sanitize_email( (string) $row['user_email'] );
				}
				$users[] = $user;
			}
		}

		$userswp = array();
		foreach ( array( 'form_fields' => array( 'uwp_form_fields', 'uform_fields' ), 'profile_tabs' => array( 'uwp_profile_tabs', 'uprofile_tabs' ), 'user_sorting' => array( 'uwp_user_sorting', 'uuser_sorting' ) ) as $key => $candidates ) {
			foreach ( $candidates as $suffix ) {
				$table = $wpdb->prefix . $suffix;
				if ( $table === $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table ) ) ) {
					$userswp[ $key ] = $this->decode_rows( (array) $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A ) );
					break;
				}
			}
		}
		$settings = get_option( 'uwp_settings', array() );
		if ( is_array( $settings ) && ! empty( $settings ) ) {
			$userswp['settings'] = array_filter(
				$settings,
				function ( $key ) {
					return ! preg_match( '/key|secret|token|password|recaptcha/i', (string) $key );
				},
				ARRAY_FILTER_USE_KEY
			);
		}

		return array(
			'schema_version' => 1,
			'emails'         => $with_email ? 'operator_opted_in' : 'not_exported',
			'passwords'      => 'never_exported',
			'users'          => $users,
			'userswp'        => $userswp,
		);
	}

	/** Decode serialized/JSON columns and drop sensitive ones. */
	private function decode_rows( array $rows ) {
		$out = array();
		foreach ( $rows as $row ) {
			if ( ! is_array( $row ) ) {
				continue;
			}
			foreach ( $row as $column => $value ) {
				if ( preg_match( '/email|password|_ip$|token/i', (string) $column ) && 'field_type' !== $column && 'htmlvar_name' !== $column ) {
					unset( $row[ $column ] );
					continue;
				}
				if ( is_string( $value ) ) {
					$decoded = maybe_unserialize( $value );
					if ( is_array( $decoded ) ) {
						$row[ $column ] = $decoded;
					} elseif ( is_numeric( $value ) && (string) (int) $value === $value ) {
						$row[ $column ] = (int) $value;
					}
				}
			}
			$out[] = $row;
		}
		return $out;
	}
}
