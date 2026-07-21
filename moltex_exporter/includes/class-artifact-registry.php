<?php
/**
 * Declarative artifact registry for the moltex-export/1 contract.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Describes every contract artifact and bounded evidence exception.
 */
class Moltex_Exporter_Artifact_Registry {

	const CONTRACT_VERSION = 'moltex-export/1';
	const MAX_FILE_COUNT = 5000;
	const MAX_TOTAL_BYTES = 262144000;
	const DEFAULT_MAX_BYTES = 10485760;

	/**
	 * Schema filenames shipped with the contract.
	 *
	 * @return array
	 */
	public static function get_schema_filenames() {
		return array(
			'bundle.schema.json',
			'content-item.schema.json',
			'export-completeness.schema.json',
			'forms-config.schema.json',
			'geodirectory.schema.json',
			'generic-object.schema.json',
			'integration-manifest.schema.json',
			'media-map.schema.json',
			'menus.schema.json',
			'migration-readiness.schema.json',
			'privacy-scan.schema.json',
			'schema-validation-report.schema.json',
			'seo-full.schema.json',
			'site-blueprint.schema.json',
			'site-settings.schema.json',
		);
	}

	/**
	 * Return registry definitions in matching priority order.
	 *
	 * @return array
	 */
	public function get_definitions() {
		$definitions = array(
			$this->definition( 'bundle.json', 'manifest', 'exporter', true, 'schemas/bundle.schema.json', 'filtered aggregate', 5242880, false ),
			$this->definition( 'site_blueprint.json', 'json', 'exporter', true, 'schemas/site-blueprint.schema.json', 'filtered aggregate' ),
			$this->definition( 'site_settings.json', 'json', 'settings', true, 'schemas/site-settings.schema.json', 'sensitive-filtered' ),
			$this->definition( 'menus.json', 'json', 'menus', true, 'schemas/menus.schema.json', 'public' ),
			$this->definition( 'export_completeness.json', 'json', 'content', true, 'schemas/export-completeness.schema.json', 'counts and status' ),
			$this->definition( 'media/media_map.json', 'json', 'media', true, 'schemas/media-map.schema.json', 'reviewed source URLs', self::DEFAULT_MAX_BYTES, false ),
			$this->definition( 'migration_readiness.json', 'json', 'migration_readiness', true, 'schemas/migration-readiness.schema.json', 'aggregate diagnostic' ),
			$this->definition( 'seo_full.json', 'json', 'seo_full', true, 'schemas/seo-full.schema.json', 'public SEO evidence' ),
			$this->definition( 'forms_config.json', 'json', 'forms', true, 'schemas/forms-config.schema.json', 'sensitive-filtered capability evidence' ),
			$this->definition( 'geodirectory.json', 'json', 'content', false, 'schemas/geodirectory.schema.json', 'public typed directory configuration' ),
			$this->definition( 'integration_manifest.json', 'json', 'integration_manifest', true, 'schemas/integration-manifest.schema.json', 'sensitive-filtered capability evidence' ),
			$this->definition( 'privacy-scan.json', 'json', 'privacy', false, 'schemas/privacy-scan.schema.json', 'checksums and scan status only', 5242880, false ),
			$this->pattern_definition( 'content/*/*.json', 'json', 'content', true, 'schemas/content-item.schema.json', 'public content with filtered metadata', self::DEFAULT_MAX_BYTES ),
			$this->pattern_definition( 'snapshots/*.html', 'html', 'content', false, null, 'sanitized public HTML', 5242880, false ),
			$this->definition( 'screenshots/manifest.json', 'json', 'media', false, 'schemas/generic-object.schema.json', 'reviewed public visual evidence' ),
			$this->pattern_definition( 'screenshots/*.png', 'image', 'media', false, null, 'reviewed public visual evidence', 10485760, false ),
			$this->pattern_definition( 'media/*', 'binary', 'media', false, null, 'public media', 52428800, false ),
			$this->pattern_definition( 'theme/*', 'evidence', 'theme', false, null, 'presentation evidence', 52428800, false ),
			$this->pattern_definition( 'assets/*', 'evidence', 'assets', false, null, 'public assets', 52428800, false ),
			$this->pattern_definition( 'plugins/*', 'evidence', 'plugins', false, null, 'structured plugin configuration and capability evidence', 52428800, false ),
			$this->definition( 'redirects_candidates.csv', 'csv', 'redirects', false, null, 'public URLs', 10485760, false ),
			$this->definition( 'schema_mysql.sql', 'sql', 'database', false, null, 'sensitive structural evidence', 10485760, false ),
		);

		$optional_json = array(
			'acf_field_groups.json'      => 'acf',
			'block_patterns.json'        => 'block_patterns',
			'blocks_usage.json'          => 'content',
			'error_log.json'             => 'exporter',
			'hooks_registry.json'        => 'hooks',
			'page_templates.json'        => 'page_templates',
			'plugin_behaviors.json'      => 'plugins',
			'plugins_fingerprint.json'   => 'plugins',
			'rest_api_endpoints.json'    => 'rest_api',
			'shortcodes_inventory.json'  => 'shortcodes',
			'site_environment.json'      => 'environment',
			'site_options.json'          => 'site_options',
			'translations.json'          => 'translations',
			'user_roles.json'            => 'user_roles',
			'widgets.json'               => 'widgets',
		);

		foreach ( $optional_json as $path => $producer ) {
			$definitions[] = $this->definition( $path, 'json', $producer, false, null, 'filtered evidence' );
		}

		foreach ( self::get_schema_filenames() as $schema_filename ) {
			$definitions[] = $this->definition(
				'schemas/' . $schema_filename,
				'schema',
				'contract',
				! in_array( $schema_filename, array( 'geodirectory.schema.json', 'privacy-scan.schema.json' ), true ),
				null,
				'public contract',
				1048576,
				false
			);
		}

		// Extensions may add bounded, review-required text evidence only inside
		// their declared namespace. There is intentionally no global wildcard.
		$definitions[] = $this->pattern_definition( 'extensions/*/*.json', 'json', 'extension', false, null, 'review required', self::DEFAULT_MAX_BYTES, false );
		$definitions[] = $this->pattern_definition( 'extensions/*/*.csv', 'csv', 'extension', false, null, 'review required', self::DEFAULT_MAX_BYTES, false );
		$definitions[] = $this->pattern_definition( 'extensions/*/*.txt', 'text', 'extension', false, null, 'review required', self::DEFAULT_MAX_BYTES, false );

		return $definitions;
	}

	/**
	 * Resolve the definition for a normalized path.
	 *
	 * @param string $path ZIP-relative path.
	 * @return array|null
	 */
	public function get_definition( $path ) {
		$path = self::normalize_relative_path( $path );

		foreach ( $this->get_definitions() as $definition ) {
			if ( isset( $definition['path'] ) && $definition['path'] === $path ) {
				return $definition;
			}

			if ( isset( $definition['pattern'] ) && $this->matches_pattern( $definition['pattern'], $path ) ) {
				return $definition;
			}
		}

		return null;
	}

	/**
	 * Return exact required paths, excluding bundle.json itself when requested.
	 *
	 * @param bool $include_bundle Include bundle.json.
	 * @return array
	 */
	public function get_required_paths( $include_bundle = true ) {
		$paths = array();
		foreach ( $this->get_definitions() as $definition ) {
			if ( empty( $definition['required'] ) || empty( $definition['path'] ) ) {
				continue;
			}
			if ( ! $include_bundle && 'bundle.json' === $definition['path'] ) {
				continue;
			}
			$paths[] = $definition['path'];
		}
		sort( $paths, SORT_STRING );
		return $paths;
	}

	/**
	 * Public registry representation included in bundle.json.
	 *
	 * @return array
	 */
	public function to_manifest_registry() {
		$definitions = $this->get_definitions();
		usort(
			$definitions,
			function( $left, $right ) {
				$left_key = isset( $left['path'] ) ? $left['path'] : $left['pattern'];
				$right_key = isset( $right['path'] ) ? $right['path'] : $right['pattern'];
				return strcmp( $left_key, $right_key );
			}
		);
		return $definitions;
	}

	/**
	 * Normalize and validate an archive-relative path.
	 *
	 * @param string $path Candidate path.
	 * @return string
	 * @throws InvalidArgumentException For unsafe paths.
	 */
	public static function normalize_relative_path( $path ) {
		if ( ! is_string( $path ) || '' === trim( $path ) || false !== strpos( $path, "\0" ) ) {
			throw new InvalidArgumentException( 'Artifact path is empty or contains a null byte.' );
		}

		$path = str_replace( '\\', '/', trim( $path ) );
		if ( '/' === substr( $path, 0, 1 ) || preg_match( '/^[A-Za-z]:\//', $path ) ) {
			throw new InvalidArgumentException( 'Absolute artifact paths are not allowed: ' . $path );
		}

		$parts = array();
		foreach ( explode( '/', $path ) as $part ) {
			if ( '' === $part || '.' === $part ) {
				continue;
			}
			if ( '..' === $part ) {
				throw new InvalidArgumentException( 'Artifact traversal is not allowed: ' . $path );
			}
			$parts[] = $part;
		}

		if ( empty( $parts ) ) {
			throw new InvalidArgumentException( 'Artifact path has no usable segments.' );
		}

		return implode( '/', $parts );
	}

	private function definition( $path, $kind, $producer, $required, $schema, $privacy, $max_bytes = self::DEFAULT_MAX_BYTES, $schema_versioned = true ) {
		return array(
			'path'               => $path,
			'kind'               => $kind,
			'producer'           => $producer,
			'required'           => (bool) $required,
			'schema'             => $schema,
			'privacy'            => $privacy,
			'max_bytes'          => (int) $max_bytes,
			'schema_versioned'   => (bool) $schema_versioned,
		);
	}

	private function pattern_definition( $pattern, $kind, $producer, $required, $schema, $privacy, $max_bytes, $schema_versioned = true ) {
		$definition = $this->definition( '', $kind, $producer, $required, $schema, $privacy, $max_bytes, $schema_versioned );
		unset( $definition['path'] );
		$definition['pattern'] = $pattern;
		return $definition;
	}

	private function matches_pattern( $pattern, $path ) {
		$quoted = preg_quote( $pattern, '#' );
		$regex = str_replace( '\*', '.*', $quoted );
		return 1 === preg_match( '#^' . $regex . '$#', $path );
	}
}
