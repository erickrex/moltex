<?php
/**
 * Translation Scanner Class
 *
 * Detects multilingual plugins and exports translation configurations,
 * language mappings, and content relationships for multilingual sites.
 *
 * Supports: WPML, Polylang, TranslatePress, Weglot
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Translation Scanner Class
 */
class Moltex_Exporter_Translation_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Detected multilingual plugin.
	 *
	 * @var string|null
	 */
	private $detected_plugin = null;

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect translation data.
	 *
	 * @return array|null Translation data or null if no multilingual plugin detected.
	 */
	public function scan() {
		// Detect which multilingual plugin is active
		$this->detect_multilingual_plugin();

		// Site-specific .po overrides (Loco Translate and hand-edited files, F3).
		$translation_files = $this->scan_translation_files( $this->get_languages_dir() );

		// If no multilingual plugin detected, return only the override files (or null).
		if ( ! $this->detected_plugin ) {
			if ( empty( $translation_files ) ) {
				return null;
			}
			return array(
				'plugin'            => null,
				'locale'            => get_locale(),
				'translation_files' => $translation_files,
			);
		}

		$data = array(
			'plugin'                => $this->detected_plugin,
			'languages'             => array(),
			'default_language'      => '',
			'content_relationships' => array(),
			'string_translations'   => array(),
			'language_switcher'     => array(),
			'url_structure'         => array(),
		);

		// Collect data based on detected plugin
		switch ( $this->detected_plugin ) {
			case 'wpml':
				$data = $this->scan_wpml( $data );
				break;
			case 'polylang':
				$data = $this->scan_polylang( $data );
				break;
			case 'translatepress':
				$data = $this->scan_translatepress( $data );
				break;
			case 'weglot':
				$data = $this->scan_weglot( $data );
				break;
		}

		$data['locale'] = get_locale();
		$data['translation_files'] = $translation_files;

		return $data;
	}

	/** @return string */
	private function get_languages_dir() {
		if ( defined( 'WP_LANG_DIR' ) ) {
			return WP_LANG_DIR;
		}
		return defined( 'WP_CONTENT_DIR' ) ? WP_CONTENT_DIR . '/languages' : '';
	}

	/**
	 * Parse custom .po files into entries (F3).
	 *
	 * Everything under `loco/` is taken. Elsewhere only files whose header names
	 * Loco or that have no WordPress.org project header are taken, so stock
	 * language packs are skipped (they can be re-downloaded).
	 *
	 * @param string $dir Languages directory.
	 * @return array[]
	 */
	public function scan_translation_files( $dir ) {
		$dir = rtrim( (string) $dir, '/' );
		if ( '' === $dir || ! is_dir( $dir ) ) {
			return array();
		}
		$files = array();
		$iterator = new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $dir, FilesystemIterator::SKIP_DOTS ) );
		foreach ( $iterator as $file ) {
			$extension = strtolower( $file->getExtension() );
			if ( ! $file->isFile() || $file->isLink() || ! in_array( $extension, array( 'po', 'mo' ), true ) || $file->getSize() > 5242880 ) {
				continue;
			}
			$sibling = substr( $file->getPathname(), 0, -2 ) . ( 'po' === $extension ? 'mo' : 'po' );
			// The .po is the editable source; a .mo beside it is its compiled copy.
			if ( 'mo' === $extension && is_file( $sibling ) ) {
				continue;
			}
			$relative = ltrim( str_replace( '\\', '/', substr( $file->getPathname(), strlen( $dir ) ) ), '/' );
			$content = (string) file_get_contents( $file->getPathname() );
			$parsed = 'po' === $extension ? self::parse_po( $content ) : self::parse_mo( $content );
			if ( null === $parsed ) {
				$this->log_warning( 'translations', 'Unreadable .mo translation file skipped: ' . $relative );
				continue;
			}
			$headers = $parsed['headers'];
			$is_loco = 0 === strpos( $relative, 'loco/' ) || false !== stripos( isset( $headers['X-Generator'] ) ? $headers['X-Generator'] : '', 'Loco' ) || isset( $headers['X-Loco-Version'] );
			$is_stock = isset( $headers['Project-Id-Version'] ) && preg_match( '/^WordPress|Plugins - |Themes - /', $headers['Project-Id-Version'] ) && ! $is_loco;
			if ( $is_stock ) {
				continue;
			}
			$basename = basename( $relative, '.' . $extension );
			$locale = preg_match( '/([a-z]{2,3}(?:_[A-Z]{2})?(?:_[a-z]+)?)$/', $basename, $m ) ? $m[1] : ( isset( $headers['Language'] ) ? $headers['Language'] : '' );
			$domain = rtrim( substr( $basename, 0, strlen( $basename ) - strlen( $locale ) ), '-' );
			$scope = 0 === strpos( $relative, 'loco/' ) ? explode( '/', $relative )[1] : explode( '/', $relative )[0];
			$files[] = array(
				'path'        => $relative,
				'format'      => $extension,
				'source'      => $is_loco ? 'loco' : 'custom',
				'scope'       => in_array( $scope, array( 'plugins', 'themes' ), true ) ? rtrim( $scope, 's' ) : 'core',
				'text_domain' => '' === $domain ? 'default' : $domain,
				'locale'      => $locale,
				'sha256'      => hash( 'sha256', $content ),
				'headers'     => array_intersect_key( $headers, array_flip( array( 'Language', 'Plural-Forms', 'X-Generator', 'X-Loco-Version', 'Project-Id-Version' ) ) ),
				'entry_count' => count( $parsed['entries'] ),
				'entries'     => $parsed['entries'],
			);
		}
		usort( $files, function ( $a, $b ) { return strcmp( $a['path'], $b['path'] ); } );
		return $files;
	}

	/**
	 * Minimal gettext .po parser: msgctxt, msgid, msgid_plural, msgstr[n].
	 *
	 * @param string $content File content.
	 * @return array {headers, entries[]}
	 */
	public static function parse_po( $content ) {
		$entries = array();
		$entry = array();
		$field = null;
		$flush = function () use ( &$entry, &$entries ) {
			if ( isset( $entry['msgid'] ) ) {
				$entries[] = $entry;
			}
			$entry = array();
		};
		foreach ( preg_split( '/\r\n|\n|\r/', $content ) as $line ) {
			$line = trim( $line );
			if ( '' === $line ) {
				$flush();
				$field = null;
				continue;
			}
			if ( '#' === $line[0] ) {
				continue;
			}
			if ( preg_match( '/^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+"(.*)"$/', $line, $m ) ) {
				if ( 'msgid' === $m[1] && isset( $entry['msgid'] ) ) {
					$flush();
				}
				$field = $m[1];
				$value = stripcslashes( $m[3] );
				if ( 0 === strpos( $field, 'msgstr' ) ) {
					$field = 'msgstr:' . ( isset( $m[2] ) && '' !== $m[2] ? $m[2] : '0' );
				}
				$entry[ $field ] = $value;
			} elseif ( null !== $field && preg_match( '/^"(.*)"$/', $line, $m ) ) {
				$entry[ $field ] .= stripcslashes( $m[1] );
			}
		}
		$flush();
		return self::finalize_entries( $entries );
	}

	/**
	 * Minimal gettext .mo reader (both byte orders). Entries come back in the
	 * same shape as parse_po(), so compiled-only overrides are not lost (F3).
	 *
	 * @param string $content Binary file content.
	 * @return array|null {headers, entries[]} or null when not a valid .mo file.
	 */
	public static function parse_mo( $content ) {
		$length = strlen( $content );
		if ( $length < 28 ) {
			return null;
		}
		$magic = unpack( 'V', substr( $content, 0, 4 ) )[1];
		if ( 0x950412de === $magic ) {
			$format = 'V';
		} elseif ( 0xde120495 === $magic ) {
			$format = 'N';
		} else {
			return null;
		}
		$header = unpack( $format . 'revision/' . $format . 'count/' . $format . 'originals/' . $format . 'translations', substr( $content, 4, 16 ) );
		$count = (int) $header['count'];
		if ( $count < 0 || $header['originals'] + 8 * $count > $length || $header['translations'] + 8 * $count > $length ) {
			return null;
		}
		$read = function ( $table, $index ) use ( $content, $format, $length ) {
			$pair = unpack( $format . 'len/' . $format . 'offset', substr( $content, $table + 8 * $index, 8 ) );
			if ( $pair['offset'] + $pair['len'] > $length ) {
				return null;
			}
			return (string) substr( $content, $pair['offset'], $pair['len'] );
		};
		$entries = array();
		for ( $i = 0; $i < $count; $i++ ) {
			$original = $read( $header['originals'], $i );
			$translation = $read( $header['translations'], $i );
			if ( null === $original || null === $translation ) {
				return null;
			}
			$entry = array();
			if ( false !== strpos( $original, "\x04" ) ) {
				list( $entry['msgctxt'], $original ) = explode( "\x04", $original, 2 );
			}
			$ids = explode( "\0", $original );
			$entry['msgid'] = $ids[0];
			if ( isset( $ids[1] ) ) {
				$entry['msgid_plural'] = $ids[1];
			}
			foreach ( explode( "\0", $translation ) as $n => $text ) {
				$entry[ 'msgstr:' . $n ] = $text;
			}
			$entries[] = $entry;
		}
		return self::finalize_entries( $entries );
	}

	/**
	 * Split the header entry from translated entries and normalize them.
	 *
	 * @param array $entries Raw entries keyed msgctxt/msgid/msgid_plural/msgstr:N.
	 * @return array {headers, entries[]}
	 */
	private static function finalize_entries( array $entries ) {
		$headers = array();
		$output = array();
		foreach ( $entries as $item ) {
			if ( '' === $item['msgid'] && ! isset( $item['msgctxt'] ) ) {
				foreach ( explode( "\n", isset( $item['msgstr:0'] ) ? $item['msgstr:0'] : '' ) as $header ) {
					if ( false !== strpos( $header, ':' ) ) {
						list( $key, $value ) = explode( ':', $header, 2 );
						$headers[ trim( $key ) ] = trim( $value );
					}
				}
				continue;
			}
			$translations = array();
			foreach ( $item as $key => $value ) {
				if ( 0 === strpos( $key, 'msgstr:' ) ) {
					$translations[ (int) substr( $key, 7 ) ] = $value;
				}
			}
			ksort( $translations );
			$output[] = array(
				'context'      => isset( $item['msgctxt'] ) ? $item['msgctxt'] : null,
				'msgid'        => $item['msgid'],
				'msgid_plural' => isset( $item['msgid_plural'] ) ? $item['msgid_plural'] : null,
				'msgstr'       => array_values( $translations ),
			);
		}
		return array( 'headers' => $headers, 'entries' => $output );
	}

	/**
	 * Detect which multilingual plugin is active.
	 */
	private function detect_multilingual_plugin() {
		// Check for WPML
		if ( defined( 'ICL_SITEPRESS_VERSION' ) || class_exists( 'SitePress' ) ) {
			$this->detected_plugin = 'wpml';
			return;
		}

		// Check for Polylang
		if ( defined( 'POLYLANG_VERSION' ) || function_exists( 'pll_languages_list' ) ) {
			$this->detected_plugin = 'polylang';
			return;
		}

		// Check for TranslatePress
		if ( defined( 'TRP_PLUGIN_VERSION' ) || class_exists( 'TRP_Translate_Press' ) ) {
			$this->detected_plugin = 'translatepress';
			return;
		}

		// Check for Weglot
		if ( defined( 'WEGLOT_VERSION' ) || class_exists( 'Weglot\Client\Client' ) ) {
			$this->detected_plugin = 'weglot';
			return;
		}
	}

	/**
	 * Scan WPML configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_wpml( $data ) {
		global $sitepress;

		if ( ! $sitepress ) {
			return $data;
		}

		// Get active languages
		$active_languages = $sitepress->get_active_languages();
		$default_language = $sitepress->get_default_language();

		$data['default_language'] = $default_language;

		// Collect language information
		foreach ( $active_languages as $lang_code => $language ) {
			$data['languages'][ $lang_code ] = array(
				'code'         => $lang_code,
				'name'         => isset( $language['display_name'] ) ? $language['display_name'] : $language['native_name'],
				'native_name'  => isset( $language['native_name'] ) ? $language['native_name'] : '',
				'locale'       => isset( $language['default_locale'] ) ? $language['default_locale'] : '',
				'is_default'   => ( $lang_code === $default_language ),
				'flag'         => isset( $language['country_flag_url'] ) ? $language['country_flag_url'] : '',
			);
		}

		// Get content relationships
		$data['content_relationships'] = $this->get_wpml_content_relationships();

		// Get string translations
		$data['string_translations'] = $this->get_wpml_string_translations();

		// Get language switcher configuration
		$data['language_switcher'] = $this->get_wpml_language_switcher_config();

		// Get URL structure
		$data['url_structure'] = $this->get_wpml_url_structure();

		return $data;
	}

	/**
	 * Get WPML content relationships.
	 *
	 * @return array Content translation relationships.
	 */
	private function get_wpml_content_relationships() {
		global $wpdb;

		$relationships = array();

		// Query translation relationships from icl_translations table
		$query = "
			SELECT 
				t.element_id,
				t.element_type,
				t.language_code,
				t.trid,
				t.source_language_code
			FROM {$wpdb->prefix}icl_translations t
			WHERE t.element_type LIKE 'post_%'
			ORDER BY t.trid, t.language_code
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			$grouped = array();
			
			foreach ( $results as $row ) {
				$trid = $row->trid;
				
				if ( ! isset( $grouped[ $trid ] ) ) {
					$grouped[ $trid ] = array();
				}
				
				$grouped[ $trid ][ $row->language_code ] = array(
					'post_id'              => $row->element_id,
					'element_type'         => $row->element_type,
					'source_language_code' => $row->source_language_code,
				);
			}

			$relationships = $grouped;
		}

		return $relationships;
	}

	/**
	 * Get WPML string translations.
	 *
	 * @return array String translations.
	 */
	private function get_wpml_string_translations() {
		global $wpdb;

		$strings = array();

		// Query string translations (limit to avoid huge exports)
		$query = "
			SELECT 
				s.name,
				s.value as original_value,
				s.context,
				st.value as translated_value,
				st.language
			FROM {$wpdb->prefix}icl_strings s
			LEFT JOIN {$wpdb->prefix}icl_string_translations st ON s.id = st.string_id
			WHERE s.context IN ('admin_texts_plugin', 'Widgets', 'Theme Options')
			LIMIT 500
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			foreach ( $results as $row ) {
				$key = $row->context . '::' . $row->name;
				
				if ( ! isset( $strings[ $key ] ) ) {
					$strings[ $key ] = array(
						'name'           => $row->name,
						'context'        => $row->context,
						'original_value' => $row->original_value,
						'translations'   => array(),
					);
				}
				
				if ( $row->language && $row->translated_value ) {
					$strings[ $key ]['translations'][ $row->language ] = $row->translated_value;
				}
			}
		}

		return array_values( $strings );
	}

	/**
	 * Get WPML language switcher configuration.
	 *
	 * @return array Language switcher settings.
	 */
	private function get_wpml_language_switcher_config() {
		$settings = get_option( 'icl_sitepress_settings', array() );

		return array(
			'skip_missing_translations' => isset( $settings['skip_missing'] ) ? $settings['skip_missing'] : false,
			'show_flags'                => isset( $settings['icl_lso_flags'] ) ? $settings['icl_lso_flags'] : false,
			'show_native_names'         => isset( $settings['icl_lso_native_lang'] ) ? $settings['icl_lso_native_lang'] : false,
			'show_display_names'        => isset( $settings['icl_lso_display_lang'] ) ? $settings['icl_lso_display_lang'] : false,
		);
	}

	/**
	 * Get WPML URL structure.
	 *
	 * @return array URL structure configuration.
	 */
	private function get_wpml_url_structure() {
		$settings = get_option( 'icl_sitepress_settings', array() );

		$language_negotiation = isset( $settings['language_negotiation_type'] ) ? $settings['language_negotiation_type'] : 1;

		$types = array(
			1 => 'directory',      // example.com/en/
			2 => 'domain',         // en.example.com
			3 => 'parameter',      // example.com?lang=en
		);

		return array(
			'type'                => isset( $types[ $language_negotiation ] ) ? $types[ $language_negotiation ] : 'directory',
			'directory_for_default_language' => isset( $settings['urls']['directory_for_default_language'] ) ? $settings['urls']['directory_for_default_language'] : false,
		);
	}

	/**
	 * Scan Polylang configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_polylang( $data ) {
		if ( ! function_exists( 'pll_languages_list' ) ) {
			return $data;
		}

		// Get languages
		$languages = pll_languages_list( array( 'fields' => '' ) );
		$default_language = pll_default_language();

		$data['default_language'] = $default_language;

		// Collect language information
		foreach ( $languages as $language ) {
			$lang_code = $language->slug;
			
			$data['languages'][ $lang_code ] = array(
				'code'        => $lang_code,
				'name'        => $language->name,
				'locale'      => $language->locale,
				'is_default'  => ( $lang_code === $default_language ),
				'is_rtl'      => (bool) $language->is_rtl,
				'flag'        => $language->flag_url,
				'home_url'    => $language->home_url,
			);
		}

		// Get content relationships
		$data['content_relationships'] = $this->get_polylang_content_relationships();

		// Get string translations
		$data['string_translations'] = $this->get_polylang_string_translations();

		// Get language switcher configuration
		$data['language_switcher'] = $this->get_polylang_language_switcher_config();

		// Get URL structure
		$data['url_structure'] = $this->get_polylang_url_structure();

		return $data;
	}

	/**
	 * Get Polylang content relationships.
	 *
	 * @return array Content translation relationships.
	 */
	private function get_polylang_content_relationships() {
		if ( ! function_exists( 'pll_get_post_translations' ) ) {
			return array();
		}

		global $wpdb;

		$relationships = array();

		// Get all posts with translations
		$query = "
			SELECT DISTINCT tr.object_id as post_id
			FROM {$wpdb->term_relationships} tr
			INNER JOIN {$wpdb->term_taxonomy} tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
			WHERE tt.taxonomy = 'language'
			LIMIT 1000
		";

		$post_ids = $wpdb->get_col( $query );

		foreach ( $post_ids as $post_id ) {
			$translations = pll_get_post_translations( $post_id );
			
			if ( $translations && count( $translations ) > 1 ) {
				// Create a unique key for this translation group
				$group_key = md5( serialize( array_values( $translations ) ) );
				
				if ( ! isset( $relationships[ $group_key ] ) ) {
					$relationships[ $group_key ] = array();
					
					foreach ( $translations as $lang => $translated_post_id ) {
						$relationships[ $group_key ][ $lang ] = array(
							'post_id' => $translated_post_id,
						);
					}
				}
			}
		}

		return $relationships;
	}

	/**
	 * Get Polylang string translations.
	 *
	 * @return array String translations.
	 */
	private function get_polylang_string_translations() {
		if ( ! function_exists( 'pll_languages_list' ) ) {
			return array();
		}

		global $wpdb;

		$strings = array();

		// Query string translations from Polylang's strings table
		$table_name = $wpdb->prefix . 'polylang_strings';
		
		if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table_name}'" ) !== $table_name ) {
			return array();
		}

		$query = "
			SELECT 
				name,
				context,
				string as original_value
			FROM {$table_name}
			LIMIT 500
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			foreach ( $results as $row ) {
				$strings[] = array(
					'name'           => $row->name,
					'context'        => $row->context,
					'original_value' => $row->original_value,
					'translations'   => array(), // Polylang stores translations differently
				);
			}
		}

		return $strings;
	}

	/**
	 * Get Polylang language switcher configuration.
	 *
	 * @return array Language switcher settings.
	 */
	private function get_polylang_language_switcher_config() {
		$options = get_option( 'polylang', array() );

		return array(
			'hide_default'     => isset( $options['hide_default'] ) ? $options['hide_default'] : false,
			'force_lang'       => isset( $options['force_lang'] ) ? $options['force_lang'] : 0,
			'hide_current'     => isset( $options['hide_current'] ) ? $options['hide_current'] : false,
			'dropdown'         => isset( $options['dropdown'] ) ? $options['dropdown'] : false,
			'show_flags'       => isset( $options['show_flags'] ) ? $options['show_flags'] : true,
			'show_names'       => isset( $options['show_names'] ) ? $options['show_names'] : false,
		);
	}

	/**
	 * Get Polylang URL structure.
	 *
	 * @return array URL structure configuration.
	 */
	private function get_polylang_url_structure() {
		$options = get_option( 'polylang', array() );

		$force_lang = isset( $options['force_lang'] ) ? $options['force_lang'] : 0;

		$types = array(
			0 => 'none',           // No language information in URL
			1 => 'directory',      // example.com/en/
			2 => 'subdomain',      // en.example.com
			3 => 'domain',         // example.en
		);

		return array(
			'type'                           => isset( $types[ $force_lang ] ) ? $types[ $force_lang ] : 'none',
			'hide_default'                   => isset( $options['hide_default'] ) ? $options['hide_default'] : false,
			'rewrite'                        => isset( $options['rewrite'] ) ? $options['rewrite'] : 1,
		);
	}

	/**
	 * Scan TranslatePress configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_translatepress( $data ) {
		$settings = get_option( 'trp_settings', array() );

		if ( empty( $settings ) ) {
			return $data;
		}

		// Get default language
		$default_language = isset( $settings['default-language'] ) ? $settings['default-language'] : '';
		$data['default_language'] = $default_language;

		// Get publish languages
		$publish_languages = isset( $settings['publish-languages'] ) ? $settings['publish-languages'] : array();

		// Get all languages (published + default)
		$all_languages = array_unique( array_merge( array( $default_language ), $publish_languages ) );

		// Collect language information
		foreach ( $all_languages as $lang_code ) {
			if ( empty( $lang_code ) ) {
				continue;
			}

			$data['languages'][ $lang_code ] = array(
				'code'       => $lang_code,
				'name'       => $this->get_language_name( $lang_code ),
				'is_default' => ( $lang_code === $default_language ),
			);
		}

		// TranslatePress doesn't have traditional content relationships
		// It translates on-the-fly and stores in custom tables
		$data['content_relationships'] = array();

		// Get string translations from TranslatePress tables
		$data['string_translations'] = $this->get_translatepress_string_translations( $all_languages );

		// Get language switcher configuration
		$data['language_switcher'] = array(
			'shortcode_enabled'  => isset( $settings['shortcode-enabled'] ) ? $settings['shortcode-enabled'] : 'yes',
			'floater_enabled'    => isset( $settings['trp_advanced_settings']['enable_language_switcher'] ) ? $settings['trp_advanced_settings']['enable_language_switcher'] : 'yes',
			'flags_in_menu'      => isset( $settings['add-flags-to-menu'] ) ? $settings['add-flags-to-menu'] : 'yes',
		);

		// Get URL structure
		$data['url_structure'] = array(
			'type'                           => 'directory',
			'add_subdirectory_to_default_language' => isset( $settings['add-subdirectory-to-default-language'] ) ? $settings['add-subdirectory-to-default-language'] : 'no',
			'force_language_in_custom_links' => isset( $settings['force-language-to-custom-links'] ) ? $settings['force-language-to-custom-links'] : 'no',
		);

		return $data;
	}

	/**
	 * Get TranslatePress string translations.
	 *
	 * @param array $languages List of language codes.
	 * @return array String translations.
	 */
	private function get_translatepress_string_translations( $languages ) {
		global $wpdb;

		$strings = array();

		foreach ( $languages as $lang_code ) {
			if ( empty( $lang_code ) ) {
				continue;
			}

			$table_name = $wpdb->prefix . 'trp_dictionary_' . strtolower( str_replace( '-', '_', $lang_code ) );

			// Check if table exists
			if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table_name}'" ) !== $table_name ) {
				continue;
			}

			// Get sample translations (limit to avoid huge exports)
			$query = $wpdb->prepare(
				"SELECT original, translated, status FROM {$table_name} WHERE status = %d LIMIT 500",
				2 // Status 2 = translated
			);

			$results = $wpdb->get_results( $query );

			if ( $results ) {
				foreach ( $results as $row ) {
					$key = md5( $row->original );
					
					if ( ! isset( $strings[ $key ] ) ) {
						$strings[ $key ] = array(
							'original_value' => $row->original,
							'translations'   => array(),
						);
					}
					
					$strings[ $key ]['translations'][ $lang_code ] = $row->translated;
				}
			}
		}

		return array_values( $strings );
	}

	/**
	 * Scan Weglot configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_weglot( $data ) {
		$options = get_option( 'weglot_options', array() );

		if ( empty( $options ) ) {
			return $data;
		}

		// Get original language
		$original_language = isset( $options['language_from'] ) ? $options['language_from'] : '';
		$data['default_language'] = $original_language;

		// Get destination languages
		$destination_languages = isset( $options['destination_language'] ) ? $options['destination_language'] : array();

		// Add original language
		if ( $original_language ) {
			$data['languages'][ $original_language ] = array(
				'code'       => $original_language,
				'name'       => $this->get_language_name( $original_language ),
				'is_default' => true,
			);
		}

		// Add destination languages
		foreach ( $destination_languages as $lang_code ) {
			$data['languages'][ $lang_code ] = array(
				'code'       => $lang_code,
				'name'       => $this->get_language_name( $lang_code ),
				'is_default' => false,
			);
		}

		// Weglot is a cloud-based service, no local content relationships
		$data['content_relationships'] = array();
		$data['string_translations'] = array();

		// Get language switcher configuration
		$data['language_switcher'] = array(
			'is_dropdown'           => isset( $options['is_dropdown'] ) ? $options['is_dropdown'] : false,
			'with_flags'            => isset( $options['with_flags'] ) ? $options['with_flags'] : true,
			'with_name'             => isset( $options['with_name'] ) ? $options['with_name'] : true,
			'flag_css'              => isset( $options['flag_css'] ) ? $options['flag_css'] : '',
		);

		// Get URL structure
		$data['url_structure'] = array(
			'type'                  => 'directory',
			'exclude_urls'          => isset( $options['exclude_urls'] ) ? $options['exclude_urls'] : array(),
			'auto_redirect'         => isset( $options['auto_redirect'] ) ? $options['auto_redirect'] : false,
		);

		return $data;
	}

	/**
	 * Get language name from code.
	 *
	 * @param string $code Language code.
	 * @return string Language name.
	 */
	private function get_language_name( $code ) {
		// Common language codes to names mapping
		$languages = array(
			'en'    => 'English',
			'en_US' => 'English (United States)',
			'en_GB' => 'English (United Kingdom)',
			'es'    => 'Spanish',
			'es_ES' => 'Spanish (Spain)',
			'fr'    => 'French',
			'fr_FR' => 'French (France)',
			'de'    => 'German',
			'de_DE' => 'German (Germany)',
			'it'    => 'Italian',
			'it_IT' => 'Italian (Italy)',
			'pt'    => 'Portuguese',
			'pt_BR' => 'Portuguese (Brazil)',
			'pt_PT' => 'Portuguese (Portugal)',
			'nl'    => 'Dutch',
			'nl_NL' => 'Dutch (Netherlands)',
			'ru'    => 'Russian',
			'ru_RU' => 'Russian (Russia)',
			'zh'    => 'Chinese',
			'zh_CN' => 'Chinese (Simplified)',
			'ja'    => 'Japanese',
			'ja_JP' => 'Japanese (Japan)',
			'ar'    => 'Arabic',
			'ar_AR' => 'Arabic',
		);

		return isset( $languages[ $code ] ) ? $languages[ $code ] : $code;
	}

}
