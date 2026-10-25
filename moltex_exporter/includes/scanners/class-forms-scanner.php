<?php
/**
 * Forms Scanner
 *
 * Detects and exports form configurations from common WordPress form plugins.
 * Supports Contact Form 7, Gravity Forms, WPForms, Ninja Forms, and Formidable Forms.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Moltex_Exporter_Forms_Scanner
 *
 * Collects form configurations from popular form plugins.
 */
class Moltex_Exporter_Forms_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Forms data collected during scan
	 *
	 * @var array
	 */
	private $forms_data = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect form configurations
	 *
	 * @return array Forms configuration data
	 */
	public function scan() {
		$forms_data = array(
			'schema_version'   => 1,
			'detected_plugins' => array(),
			'forms'            => array(),
			'forms_in_content' => array(),
			'summary'          => array(
				'total_forms'     => 0,
				'forms_by_plugin' => array(),
			),
		);

		// Detect and export Contact Form 7
		if ( $this->is_plugin_active( 'contact-form-7/wp-contact-form-7.php' ) ) {
			$forms_data['detected_plugins'][] = 'contact-form-7';
			$cf7_forms = $this->export_contact_form_7();
			if ( ! empty( $cf7_forms ) ) {
				$forms_data['forms']['contact_form_7'] = $cf7_forms;
				$forms_data['summary']['forms_by_plugin']['contact_form_7'] = count( $cf7_forms );
			}
		}

		// Detect and export Gravity Forms
		if ( $this->is_plugin_active( 'gravityforms/gravityforms.php' ) ) {
			$forms_data['detected_plugins'][] = 'gravityforms';
			$gf_forms = $this->export_gravity_forms();
			if ( ! empty( $gf_forms ) ) {
				$forms_data['forms']['gravity_forms'] = $gf_forms;
				$forms_data['summary']['forms_by_plugin']['gravity_forms'] = count( $gf_forms );
			}
		}

		// Detect and export WPForms
		if ( $this->is_plugin_active( 'wpforms-lite/wpforms.php' ) || $this->is_plugin_active( 'wpforms/wpforms.php' ) ) {
			$forms_data['detected_plugins'][] = 'wpforms';
			$wpf_forms = $this->export_wpforms();
			if ( ! empty( $wpf_forms ) ) {
				$forms_data['forms']['wpforms'] = $wpf_forms;
				$forms_data['summary']['forms_by_plugin']['wpforms'] = count( $wpf_forms );
			}
		}

		// Detect and export Ninja Forms
		if ( $this->is_plugin_active( 'ninja-forms/ninja-forms.php' ) ) {
			$forms_data['detected_plugins'][] = 'ninja-forms';
			$nf_forms = $this->export_ninja_forms();
			if ( ! empty( $nf_forms ) ) {
				$forms_data['forms']['ninja_forms'] = $nf_forms;
				$forms_data['summary']['forms_by_plugin']['ninja_forms'] = count( $nf_forms );
			}
		}

		// Detect and export Forminator definitions (F1). Submissions are never exported.
		if ( $this->is_plugin_active( 'forminator/forminator.php' ) || post_type_exists( 'forminator_forms' ) ) {
			$forms_data['detected_plugins'][] = 'forminator';
			$frmt_forms = $this->export_forminator();
			if ( ! empty( $frmt_forms ) ) {
				$forms_data['forms']['forminator'] = $frmt_forms;
				$forms_data['summary']['forms_by_plugin']['forminator'] = count( $frmt_forms );
			}
		}

		// Detect and export Formidable Forms
		if ( $this->is_plugin_active( 'formidable/formidable.php' ) ) {
			$forms_data['detected_plugins'][] = 'formidable';
			$frm_forms = $this->export_formidable_forms();
			if ( ! empty( $frm_forms ) ) {
				$forms_data['forms']['formidable_forms'] = $frm_forms;
				$forms_data['summary']['forms_by_plugin']['formidable_forms'] = count( $frm_forms );
			}
		}

		// Popup Maker popups with their assigned theme design (S3).
		$popups = $this->export_popup_maker();
		if ( ! empty( $popups ) ) {
			$forms_data['popups']['popup_maker'] = $popups;
		}

		// MailPoet lists always; subscribers only with operator opt-in (F5).
		$newsletter = $this->export_mailpoet();
		if ( ! empty( $newsletter ) ) {
			$forms_data['newsletter']['mailpoet'] = $newsletter;
		}

		// Calculate total forms
		$forms_data['summary']['total_forms'] = array_sum( $forms_data['summary']['forms_by_plugin'] );

		// Scan content for embedded forms
		$forms_data['forms_in_content'] = $this->scan_content_for_forms();

		// Store for get_data()
		$this->forms_data = $forms_data;

		return $forms_data;
	}

	/**
	 * Export Contact Form 7 configurations
	 *
	 * @return array CF7 forms data
	 */
	private function export_contact_form_7() {
		if ( ! class_exists( 'WPCF7_ContactForm' ) ) {
			return array();
		}

		$forms = array();
		$cf7_posts = get_posts( array(
			'post_type'      => 'wpcf7_contact_form',
			'posts_per_page' => -1,
			'post_status'    => 'publish',
		) );

		foreach ( $cf7_posts as $post ) {
			$contact_form = WPCF7_ContactForm::get_instance( $post->ID );
			if ( ! $contact_form ) {
				continue;
			}

			$properties = $contact_form->get_properties();
			$mail       = isset( $properties['mail'] ) ? $properties['mail'] : array();
			$mail_2     = isset( $properties['mail_2'] ) ? $properties['mail_2'] : array();

			$form_data = array(
				'id'              => $post->ID,
				'title'           => $post->post_title,
				'slug'            => $post->post_name,
				'form_template'   => isset( $properties['form'] ) ? $properties['form'] : '',
				'fields'          => $this->parse_cf7_fields( isset( $properties['form'] ) ? $properties['form'] : '' ),
				'mail_settings'   => array(
					'active'             => ! empty( $mail['active'] ),
					'recipient'          => isset( $mail['recipient'] ) ? $mail['recipient'] : '',
					'sender'             => isset( $mail['sender'] ) ? $mail['sender'] : '',
					'subject'            => isset( $mail['subject'] ) ? $mail['subject'] : '',
					'body'               => isset( $mail['body'] ) ? $mail['body'] : '',
					'additional_headers' => isset( $mail['additional_headers'] ) ? $mail['additional_headers'] : '',
				),
				'mail_2_settings' => array(
					'active'    => ! empty( $mail_2['active'] ),
					'recipient' => isset( $mail_2['recipient'] ) ? $mail_2['recipient'] : '',
					'subject'   => isset( $mail_2['subject'] ) ? $mail_2['subject'] : '',
				),
				'messages'        => isset( $properties['messages'] ) ? $properties['messages'] : array(),
				'shortcode'       => '[contact-form-7 id="' . $post->ID . '" title="' . esc_attr( $post->post_title ) . '"]',
			);

			$forms[] = $form_data;
		}

		return $forms;
	}

	/**
	 * Parse Contact Form 7 field tags
	 *
	 * @param string $form_template CF7 form template.
	 * @return array Parsed fields.
	 */
	private function parse_cf7_fields( $form_template ) {
		$fields = array();

		// Match CF7 field tags like [text* your-name] or [email* your-email]
		preg_match_all( '/\[([^\]]+)\]/', $form_template, $matches );

		if ( ! empty( $matches[1] ) ) {
			foreach ( $matches[1] as $tag ) {
				$parts = preg_split( '/\s+/', $tag );
				if ( empty( $parts ) ) {
					continue;
				}

				$type     = $parts[0];
				$required = false;

				// Check if required (marked with *)
				if ( substr( $type, -1 ) === '*' ) {
					$required = true;
					$type     = substr( $type, 0, -1 );
				}

				$name = isset( $parts[1] ) ? $parts[1] : '';

				// Skip submit buttons
				if ( 'submit' === $type ) {
					continue;
				}

				$field = array(
					'type'     => $type,
					'name'     => $name,
					'required' => $required,
					'options'  => array_slice( $parts, 2 ),
				);

				$fields[] = $field;
			}
		}

		return $fields;
	}

	/**
	 * Export Gravity Forms configurations
	 *
	 * @return array Gravity Forms data
	 */
	private function export_gravity_forms() {
		if ( ! class_exists( 'GFAPI' ) ) {
			return array();
		}

		$forms    = array();
		$gf_forms = GFAPI::get_forms();

		foreach ( $gf_forms as $form ) {
			$form_data = array(
				'id'            => $form['id'],
				'title'         => $form['title'],
				'description'   => isset( $form['description'] ) ? $form['description'] : '',
				'fields'        => array(),
				'notifications' => isset( $form['notifications'] ) ? $form['notifications'] : array(),
				'confirmations' => isset( $form['confirmations'] ) ? $form['confirmations'] : array(),
				'is_active'     => isset( $form['is_active'] ) ? $form['is_active'] : true,
				'shortcode'     => '[gravityform id="' . $form['id'] . '" title="false"]',
			);

			// Export fields
			if ( ! empty( $form['fields'] ) ) {
				foreach ( $form['fields'] as $field ) {
					$field_data = array(
						'id'            => $field->id,
						'type'          => $field->type,
						'label'         => $field->label,
						'description'   => isset( $field->description ) ? $field->description : '',
						'is_required'   => ! empty( $field->isRequired ),
						'placeholder'   => isset( $field->placeholder ) ? $field->placeholder : '',
						'default_value' => isset( $field->defaultValue ) ? $field->defaultValue : '',
						'css_class'     => isset( $field->cssClass ) ? $field->cssClass : '',
					);

					// Add choices for select/radio/checkbox fields
					if ( isset( $field->choices ) && ! empty( $field->choices ) ) {
						$field_data['choices'] = $field->choices;
					}

					// Add validation rules
					if ( isset( $field->validation ) ) {
						$field_data['validation'] = $field->validation;
					}

					$form_data['fields'][] = $field_data;
				}
			}

			$forms[] = $form_data;
		}

		return $forms;
	}

	/**
	 * Export WPForms configurations
	 *
	 * @return array WPForms data
	 */
	private function export_wpforms() {
		$forms     = array();
		$wpf_posts = get_posts( array(
			'post_type'      => 'wpforms',
			'posts_per_page' => -1,
			'post_status'    => 'publish',
		) );

		foreach ( $wpf_posts as $post ) {
			$form_data_raw = get_post_meta( $post->ID, 'wpforms', true );

			if ( empty( $form_data_raw ) ) {
				continue;
			}

			$form_data = maybe_unserialize( $form_data_raw );

			$export_data = array(
				'id'            => $post->ID,
				'title'         => $post->post_title,
				'description'   => isset( $form_data['settings']['form_desc'] ) ? $form_data['settings']['form_desc'] : '',
				'fields'        => array(),
				'settings'      => isset( $form_data['settings'] ) ? $form_data['settings'] : array(),
				'notifications' => isset( $form_data['settings']['notifications'] ) ? $form_data['settings']['notifications'] : array(),
				'shortcode'     => '[wpforms id="' . $post->ID . '"]',
			);

			// Export fields
			if ( ! empty( $form_data['fields'] ) ) {
				foreach ( $form_data['fields'] as $field_id => $field ) {
					$field_export = array(
						'id'            => $field_id,
						'type'          => isset( $field['type'] ) ? $field['type'] : '',
						'label'         => isset( $field['label'] ) ? $field['label'] : '',
						'description'   => isset( $field['description'] ) ? $field['description'] : '',
						'required'      => ! empty( $field['required'] ),
						'placeholder'   => isset( $field['placeholder'] ) ? $field['placeholder'] : '',
						'default_value' => isset( $field['default_value'] ) ? $field['default_value'] : '',
						'css'           => isset( $field['css'] ) ? $field['css'] : '',
					);

					// Add choices for select/radio/checkbox fields
					if ( isset( $field['choices'] ) && ! empty( $field['choices'] ) ) {
						$field_export['choices'] = $field['choices'];
					}

					// Add validation
					if ( isset( $field['validation'] ) ) {
						$field_export['validation'] = $field['validation'];
					}

					$export_data['fields'][] = $field_export;
				}
			}

			$forms[] = $export_data;
		}

		return $forms;
	}

	/**
	 * Export Ninja Forms configurations
	 *
	 * @return array Ninja Forms data
	 */
	private function export_ninja_forms() {
		if ( ! class_exists( 'Ninja_Forms' ) ) {
			return array();
		}

		$forms    = array();
		$nf_forms = Ninja_Forms()->form()->get_forms();

		foreach ( $nf_forms as $form ) {
			$form_id       = $form->get_id();
			$form_settings = $form->get_settings();

			$form_data = array(
				'id'        => $form_id,
				'title'     => $form->get_setting( 'title' ),
				'fields'    => array(),
				'actions'   => array(),
				'settings'  => $form_settings,
				'shortcode' => '[ninja_form id="' . $form_id . '"]',
			);

			// Export fields
			$fields = Ninja_Forms()->form( $form_id )->get_fields();
			foreach ( $fields as $field ) {
				$field_settings = $field->get_settings();

				$field_data = array(
					'id'            => $field->get_id(),
					'type'          => $field->get_setting( 'type' ),
					'label'         => $field->get_setting( 'label' ),
					'key'           => $field->get_setting( 'key' ),
					'required'      => ! empty( $field->get_setting( 'required' ) ),
					'placeholder'   => $field->get_setting( 'placeholder' ),
					'default_value' => $field->get_setting( 'default' ),
					'description'   => $field->get_setting( 'desc_text' ),
					'settings'      => $field_settings,
				);

				// Add options for select/radio/checkbox fields
				$options = $field->get_setting( 'options' );
				if ( ! empty( $options ) ) {
					$field_data['options'] = $options;
				}

				$form_data['fields'][] = $field_data;
			}

			// Export actions (email notifications, etc.)
			$actions = Ninja_Forms()->form( $form_id )->get_actions();
			foreach ( $actions as $action ) {
				$action_settings = $action->get_settings();

				$action_data = array(
					'id'       => $action->get_id(),
					'type'     => $action->get_setting( 'type' ),
					'active'   => ! empty( $action->get_setting( 'active' ) ),
					'settings' => $action_settings,
				);

				$form_data['actions'][] = $action_data;
			}

			$forms[] = $form_data;
		}

		return $forms;
	}

	/**
	 * Export Formidable Forms configurations
	 *
	 * @return array Formidable Forms data
	 */
	private function export_formidable_forms() {
		if ( ! class_exists( 'FrmForm' ) ) {
			return array();
		}

		$forms     = array();
		$frm_forms = FrmForm::get_published_forms();

		foreach ( $frm_forms as $form ) {
			$form_data = array(
				'id'          => $form->id,
				'key'         => $form->form_key,
				'title'       => $form->name,
				'description' => $form->description,
				'fields'      => array(),
				'actions'     => array(),
				'options'     => maybe_unserialize( $form->options ),
				'shortcode'   => '[formidable id="' . $form->id . '"]',
			);

			// Export fields
			if ( class_exists( 'FrmField' ) ) {
				$fields = FrmField::get_all_for_form( $form->id );

				foreach ( $fields as $field ) {
					$field_data = array(
						'id'            => $field->id,
						'key'           => $field->field_key,
						'type'          => $field->type,
						'name'          => $field->name,
						'description'   => $field->description,
						'required'      => ! empty( $field->required ),
						'placeholder'   => $field->placeholder,
						'default_value' => $field->default_value,
						'options'       => maybe_unserialize( $field->options ),
						'field_options' => maybe_unserialize( $field->field_options ),
					);

					$form_data['fields'][] = $field_data;
				}
			}

			// Export actions (email notifications, etc.)
			if ( class_exists( 'FrmFormAction' ) ) {
				$actions = FrmFormAction::get_action_for_form( $form->id );

				foreach ( $actions as $action ) {
					$action_data = array(
						'id'       => $action->ID,
						'type'     => $action->post_excerpt,
						'settings' => maybe_unserialize( $action->post_content ),
					);

					$form_data['actions'][] = $action_data;
				}
			}

			$forms[] = $form_data;
		}

		return $forms;
	}

	/**
	 * Scan content for embedded forms
	 *
	 * @return array Forms found in content
	 */
	private function scan_content_for_forms() {
		$forms_in_content = array();

		// Get sample content (posts, pages, custom post types)
		$post_types = get_post_types( array( 'public' => true ), 'names' );

		$posts = get_posts( array(
			'post_type'      => $post_types,
			'posts_per_page' => 100,
			'post_status'    => 'publish',
		) );

		foreach ( $posts as $post ) {
			$content     = $post->post_content;
			$found_forms = array();

			// Check for Contact Form 7 shortcodes
			if ( preg_match_all( '/\[contact-form-7[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches ) ) {
				foreach ( $matches[1] as $form_id ) {
					$found_forms[] = array(
						'plugin'    => 'contact_form_7',
						'form_id'   => $form_id,
						'shortcode' => $matches[0][0],
					);
				}
			}

			// Check for Gravity Forms shortcodes
			if ( preg_match_all( '/\[gravityform[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches ) ) {
				foreach ( $matches[1] as $form_id ) {
					$found_forms[] = array(
						'plugin'    => 'gravity_forms',
						'form_id'   => $form_id,
						'shortcode' => $matches[0][0],
					);
				}
			}

			// Check for WPForms shortcodes
			if ( preg_match_all( '/\[wpforms[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches ) ) {
				foreach ( $matches[1] as $form_id ) {
					$found_forms[] = array(
						'plugin'    => 'wpforms',
						'form_id'   => $form_id,
						'shortcode' => $matches[0][0],
					);
				}
			}

			// Check for Ninja Forms shortcodes
			if ( preg_match_all( '/\[ninja_form[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches ) ) {
				foreach ( $matches[1] as $form_id ) {
					$found_forms[] = array(
						'plugin'    => 'ninja_forms',
						'form_id'   => $form_id,
						'shortcode' => $matches[0][0],
					);
				}
			}

			// Check for Formidable Forms shortcodes
			if ( preg_match_all( '/\[formidable[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches ) ) {
				foreach ( $matches[1] as $form_id ) {
					$found_forms[] = array(
						'plugin'    => 'formidable_forms',
						'form_id'   => $form_id,
						'shortcode' => $matches[0][0],
					);
				}
			}

			// Check for form blocks in Gutenberg content
			if ( has_blocks( $content ) ) {
				$blocks = parse_blocks( $content );
				$this->scan_blocks_for_forms( $blocks, $found_forms );
			}

			if ( ! empty( $found_forms ) ) {
				$forms_in_content[] = array(
					'post_id'    => $post->ID,
					'post_type'  => $post->post_type,
					'post_title' => $post->post_title,
					'post_url'   => get_permalink( $post->ID ),
					'forms'      => $found_forms,
				);
			}
		}

		return $forms_in_content;
	}

	/**
	 * Recursively scan blocks for form references
	 *
	 * @param array $blocks      Parsed blocks.
	 * @param array &$found_forms Reference to found forms array.
	 */
	private function scan_blocks_for_forms( $blocks, &$found_forms ) {
		foreach ( $blocks as $block ) {
			// Check for form blocks
			if ( isset( $block['blockName'] ) ) {
				// Contact Form 7 block
				if ( 'contact-form-7/contact-form-selector' === $block['blockName'] && isset( $block['attrs']['id'] ) ) {
					$found_forms[] = array(
						'plugin'  => 'contact_form_7',
						'form_id' => $block['attrs']['id'],
						'block'   => $block['blockName'],
					);
				}

				// Gravity Forms block
				if ( 'gravityforms/form' === $block['blockName'] && isset( $block['attrs']['formId'] ) ) {
					$found_forms[] = array(
						'plugin'  => 'gravity_forms',
						'form_id' => $block['attrs']['formId'],
						'block'   => $block['blockName'],
					);
				}

				// WPForms block
				if ( 'wpforms/form-selector' === $block['blockName'] && isset( $block['attrs']['formId'] ) ) {
					$found_forms[] = array(
						'plugin'  => 'wpforms',
						'form_id' => $block['attrs']['formId'],
						'block'   => $block['blockName'],
					);
				}

				// Ninja Forms block
				if ( 'ninja-forms/form' === $block['blockName'] && isset( $block['attrs']['formID'] ) ) {
					$found_forms[] = array(
						'plugin'  => 'ninja_forms',
						'form_id' => $block['attrs']['formID'],
						'block'   => $block['blockName'],
					);
				}

				// Formidable Forms block
				if ( 'formidable/simple-form' === $block['blockName'] && isset( $block['attrs']['formId'] ) ) {
					$found_forms[] = array(
						'plugin'  => 'formidable_forms',
						'form_id' => $block['attrs']['formId'],
						'block'   => $block['blockName'],
					);
				}
			}

			// Recursively check inner blocks
			if ( ! empty( $block['innerBlocks'] ) ) {
				$this->scan_blocks_for_forms( $block['innerBlocks'], $found_forms );
			}
		}
	}

	/**
	 * Check if a plugin is active
	 *
	 * @param string $plugin Plugin path.
	 * @return bool
	 */
	/**
	 * Popup Maker: popups (triggers, cookies, conditions) and popup_theme designs (S3).
	 *
	 * @return array
	 */
	public function export_popup_maker() {
		$themes = array();
		foreach ( (array) get_posts( array( 'post_type' => 'popup_theme', 'numberposts' => -1, 'post_status' => 'any' ) ) as $post ) {
			$settings = maybe_unserialize( get_post_meta( $post->ID, 'popup_theme_settings', true ) );
			$themes[ (int) $post->ID ] = array(
				'id'       => (int) $post->ID,
				'title'    => (string) $post->post_title,
				'settings' => is_array( $settings ) ? $settings : array(),
			);
		}
		$popups = array();
		foreach ( (array) get_posts( array( 'post_type' => 'popup', 'numberposts' => -1, 'post_status' => 'any' ) ) as $post ) {
			$settings = maybe_unserialize( get_post_meta( $post->ID, 'popup_settings', true ) );
			$settings = is_array( $settings ) ? $settings : array();
			$theme_id = isset( $settings['theme_id'] ) ? (int) $settings['theme_id'] : (int) get_post_meta( $post->ID, 'popup_theme', true );
			$popups[] = array(
				'id'         => (int) $post->ID,
				'title'      => (string) $post->post_title,
				'status'     => (string) $post->post_status,
				'theme_id'   => $theme_id ?: null,
				'theme'      => isset( $themes[ $theme_id ] ) ? $themes[ $theme_id ]['title'] : null,
				'triggers'   => isset( $settings['triggers'] ) ? array_values( (array) $settings['triggers'] ) : array(),
				'cookies'    => isset( $settings['cookies'] ) ? array_values( (array) $settings['cookies'] ) : array(),
				'conditions' => isset( $settings['conditions'] ) ? array_values( (array) $settings['conditions'] ) : array(),
				'size'       => array_intersect_key( $settings, array_flip( array( 'size', 'responsive_min_width', 'responsive_max_width', 'custom_width', 'custom_height', 'location', 'animation_type', 'animation_speed', 'overlay_disabled', 'close_on_overlay_click', 'close_on_esc_press', 'close_text' ) ) ),
				'settings'   => $settings,
			);
		}
		if ( empty( $popups ) && empty( $themes ) ) {
			return array();
		}
		return array(
			'popups' => $popups,
			'themes' => array_values( $themes ),
		);
	}

	private function export_mailpoet() {
		global $wpdb;
		$segments = $wpdb->prefix . 'mailpoet_segments';
		if ( $segments !== $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $segments ) ) ) {
			return array();
		}
		$links = $wpdb->prefix . 'mailpoet_subscriber_segment';
		$subscribers = $wpdb->prefix . 'mailpoet_subscribers';
		$lists = array();
		foreach ( (array) $wpdb->get_results( "SELECT s.id, s.name, s.type, s.description, s.deleted_at, COUNT(l.id) AS subscriber_count, SUM(CASE WHEN l.status = 'subscribed' THEN 1 ELSE 0 END) AS subscribed_count FROM {$segments} s LEFT JOIN {$links} l ON l.segment_id = s.id GROUP BY s.id ORDER BY s.id ASC", ARRAY_A ) as $row ) {
			$lists[] = array(
				'id'               => (int) $row['id'],
				'name'             => (string) $row['name'],
				'type'             => isset( $row['type'] ) ? (string) $row['type'] : '',
				'description'      => isset( $row['description'] ) ? (string) $row['description'] : '',
				'deleted'          => ! empty( $row['deleted_at'] ),
				'subscriber_count' => (int) $row['subscriber_count'],
				'subscribed_count' => (int) $row['subscribed_count'],
			);
		}
		$out = array( 'lists' => $lists, 'subscribers' => 'not_exported_without_opt_in' );
		if ( Moltex_Exporter_Export_Policy::get( 'include_subscribers' ) ) {
			$people = array();
			foreach ( (array) $wpdb->get_results( "SELECT sub.id, sub.email, sub.status, sub.created_at, sub.confirmed_at, sub.last_subscribed_at, GROUP_CONCAT(l.segment_id ORDER BY l.segment_id) AS segment_ids FROM {$subscribers} sub LEFT JOIN {$links} l ON l.subscriber_id = sub.id AND l.status = 'subscribed' GROUP BY sub.id ORDER BY sub.id ASC", ARRAY_A ) as $row ) {
				$people[] = array(
					'email'        => sanitize_email( (string) $row['email'] ),
					'status'       => (string) $row['status'],
					'list_ids'     => '' === (string) $row['segment_ids'] || null === $row['segment_ids'] ? array() : array_map( 'intval', explode( ',', (string) $row['segment_ids'] ) ),
					'consent_date' => ! empty( $row['confirmed_at'] ) ? (string) $row['confirmed_at'] : ( ! empty( $row['last_subscribed_at'] ) ? (string) $row['last_subscribed_at'] : (string) $row['created_at'] ),
				);
			}
			$out['subscribers'] = $people;
			$out['personal_data'] = 'operator_opted_in';
		}
		return $out;
	}

	private function export_forminator() {
		$forms = array();
		$posts = get_posts(
			array(
				'post_type'      => array( 'forminator_forms', 'forminator_polls', 'forminator_quizzes' ),
				'post_status'    => 'any',
				'posts_per_page' => -1,
				'orderby'        => 'ID',
				'order'          => 'ASC',
			)
		);
		foreach ( (array) $posts as $post ) {
			$meta = maybe_unserialize( get_post_meta( $post->ID, 'forminator_form_meta', true ) );
			$meta = is_array( $meta ) ? $meta : array();
			$fields = array();
			foreach ( isset( $meta['fields'] ) && is_array( $meta['fields'] ) ? $meta['fields'] : array() as $field ) {
				if ( ! is_array( $field ) ) {
					continue;
				}
				$fields[] = array(
					'id'         => isset( $field['element_id'] ) ? (string) $field['element_id'] : ( isset( $field['id'] ) ? (string) $field['id'] : '' ),
					'type'       => isset( $field['type'] ) ? (string) $field['type'] : '',
					'label'      => isset( $field['field_label'] ) ? (string) $field['field_label'] : '',
					'required'   => ! empty( $field['required'] ) && 'false' !== $field['required'],
					'wrapper_id' => isset( $field['wrapper_id'] ) ? (string) $field['wrapper_id'] : '',
					'definition' => $field,
				);
			}
			$settings = isset( $meta['settings'] ) && is_array( $meta['settings'] ) ? $meta['settings'] : array();
			$forms[] = array(
				'id'            => (int) $post->ID,
				'kind'          => str_replace( 'forminator_', '', (string) $post->post_type ),
				'title'         => isset( $settings['formName'] ) ? (string) $settings['formName'] : (string) $post->post_title,
				'status'        => (string) $post->post_status,
				'fields'        => $fields,
				'settings'      => $settings,
				'notifications' => isset( $meta['notifications'] ) && is_array( $meta['notifications'] ) ? $meta['notifications'] : array(),
				'integrations'  => isset( $meta['integrations'] ) && is_array( $meta['integrations'] ) ? array_keys( $meta['integrations'] ) : array(),
				// Destination details (list, sheet, field mapping) kept; credentials redacted (F1).
				'integration_settings' => isset( $meta['integrations'] ) && is_array( $meta['integrations'] ) ? self::redact_integration_settings( $meta['integrations'] ) : array(),
				'submissions'   => 'not_exported',
			);
		}
		return $forms;
	}

	/**
	 * Keep integration configuration but replace every credential with
	 * "[REDACTED]": values under credential-like keys, webhook URLs (which
	 * authorize by themselves) and credential-shaped strings.
	 *
	 * @param mixed $value Integration settings.
	 * @param int   $depth Recursion depth.
	 * @return mixed
	 */
	public static function redact_integration_settings( $value, $depth = 0 ) {
		if ( $depth > 20 ) {
			return '[TRUNCATED]';
		}
		if ( is_array( $value ) ) {
			$out = array();
			foreach ( $value as $key => $item ) {
				if ( is_string( $key ) && preg_match( '/key|secret|token|passw|pwd|auth|credential|webhook|hook_url|signature|bearer|cookie|session/i', $key ) && ! is_array( $item ) ) {
					$out[ $key ] = '' === (string) $item ? '' : '[REDACTED]';
					continue;
				}
				$out[ $key ] = self::redact_integration_settings( $item, $depth + 1 );
			}
			return $out;
		}
		if ( is_string( $value ) ) {
			if ( preg_match( '#^https?://(?:hooks\.|[^/]*zapier\.com/hooks|[^/]*/webhook)#i', $value ) ) {
				return '[REDACTED]';
			}
			return Moltex_Exporter_Privacy_Scanner::redact_credentials( $value )['text'];
		}
		return $value;
	}

	private function is_plugin_active( $plugin ) {
		if ( ! function_exists( 'is_plugin_active' ) ) {
			include_once ABSPATH . 'wp-admin/includes/plugin.php';
		}
		return is_plugin_active( $plugin );
	}
}
