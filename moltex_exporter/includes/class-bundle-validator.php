<?php
/**
 * Standalone ZIP validator for moltex-export/1.
 *
 * @package Moltex_Exporter
 */

require_once __DIR__ . '/class-site-identity.php';

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Validates archive safety, inventory, checksums, schemas, and completeness.
 */
class Moltex_Exporter_Bundle_Validator {

	private $registry;
	private $schema_validator;

	public function __construct( Moltex_Exporter_Artifact_Registry $registry = null, Moltex_Exporter_Schema_Validator $schema_validator = null ) {
		$this->registry = $registry ?: new Moltex_Exporter_Artifact_Registry();
		$this->schema_validator = $schema_validator ?: new Moltex_Exporter_Schema_Validator();
	}

	/**
	 * Validate a ZIP without extracting it.
	 *
	 * @param string $zip_path ZIP path.
	 * @return array Stable validation result.
	 */
	public function validate_zip( $zip_path ) {
		$errors = array();
		$warnings = array();
		$zip = new ZipArchive();

		if ( ! is_file( $zip_path ) || true !== $zip->open( $zip_path ) ) {
			return $this->result( false, array( 'ZIP cannot be opened.' ), array(), null, 0 );
		}

		try {
			$entries = $this->read_entries( $zip, $errors );
			if ( ! isset( $entries['bundle.json'] ) ) {
				$errors[] = 'bundle.json is missing.';
				return $this->result( false, $errors, $warnings, null, count( $entries ) );
			}

			$manifest = $this->decode_json_entry( $zip, $entries['bundle.json']['index'], 'bundle.json', $errors );
			if ( ! is_array( $manifest ) ) {
				return $this->result( false, $errors, $warnings, null, count( $entries ) );
			}

			$this->validate_manifest_schema( $zip, $entries, $manifest, $errors );
			$this->validate_site_identity( $manifest, $errors );
			$this->validate_inventory( $zip, $entries, $manifest, $errors );
			$this->validate_bundle_identity( $manifest, $errors );
			$this->validate_completeness( $zip, $entries, $manifest, $errors );
			$valid = empty( $errors );
			$complete_migration_eligible = $valid
				&& isset( $manifest['mode'] ) && 'complete' === $manifest['mode']
				&& ! empty( $manifest['complete'] );

			return $this->result(
				$valid,
				$errors,
				$warnings,
				isset( $manifest['bundle_id'] ) ? $manifest['bundle_id'] : null,
				count( $entries ),
				$complete_migration_eligible
			);
		} finally {
			$zip->close();
		}
	}

	/**
	 * Verify that the declared domain and workspace slug match site_origin.
	 *
	 * @param array $manifest Bundle manifest.
	 * @param array $errors   Validation errors.
	 */
	private function validate_site_identity( array $manifest, array &$errors ) {
		$version = isset( $manifest['exporter_version'] ) ? (string) $manifest['exporter_version'] : '0.0.0';
		if ( empty( $manifest['site_identity'] ) || ! is_array( $manifest['site_identity'] ) ) {
			if ( version_compare( $version, '1.2.10', '>=' ) ) {
				$errors[] = 'site_identity is required for exporter 1.2.10 and newer.';
			}
			return;
		}

		try {
			$expected = Moltex_Exporter_Site_Identity::from_values(
				isset( $manifest['site_origin'] ) ? $manifest['site_origin'] : '',
				isset( $manifest['site_identity']['site_name'] ) ? $manifest['site_identity']['site_name'] : ''
			);
		} catch ( InvalidArgumentException $error ) {
			$errors[] = $error->getMessage();
			return;
		}

		if ( ! isset( $manifest['site_identity']['domain'] ) || $expected['domain'] !== $manifest['site_identity']['domain'] ) {
			$errors[] = 'site_identity.domain does not match site_origin.';
		}
		if ( ! isset( $manifest['site_identity']['workspace_slug'] ) || $expected['workspace_slug'] !== $manifest['site_identity']['workspace_slug'] ) {
			$errors[] = 'site_identity.workspace_slug does not match site_origin.';
		}
	}

	private function read_entries( ZipArchive $zip, array &$errors ) {
		$entries = array();
		$total_bytes = 0;

		if ( $zip->numFiles > Moltex_Exporter_Artifact_Registry::MAX_FILE_COUNT + 100 ) {
			$errors[] = 'ZIP exceeds the entry-count limit.';
		}

		for ( $index = 0; $index < $zip->numFiles; $index++ ) {
			$stat = $zip->statIndex( $index );
			if ( false === $stat || ! isset( $stat['name'] ) ) {
				$errors[] = 'ZIP entry metadata cannot be read at index ' . $index . '.';
				continue;
			}
			$name = $stat['name'];
			if ( '/' === substr( $name, -1 ) ) {
				continue;
			}

			try {
				$path = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $name );
			} catch ( InvalidArgumentException $exception ) {
				$errors[] = 'Unsafe ZIP entry: ' . $name . '.';
				continue;
			}

			$key = strtolower( $path );
			foreach ( $entries as $existing_path => $unused ) {
				if ( strtolower( $existing_path ) === $key ) {
					$errors[] = 'Duplicate normalized ZIP entry: ' . $path . '.';
					continue 2;
				}
			}

			if ( $this->is_symlink( $zip, $index ) ) {
				$errors[] = 'Symlink ZIP entry is not allowed: ' . $path . '.';
				continue;
			}

			$size = isset( $stat['size'] ) ? (int) $stat['size'] : 0;
			$total_bytes += $size;
			$definition = $this->registry->get_definition( $path );
			if ( $definition && $size > (int) $definition['max_bytes'] ) {
				$errors[] = 'ZIP entry exceeds its declared byte limit: ' . $path . '.';
			}
			$entries[ $path ] = array( 'index' => $index, 'size' => $size );
		}

		if ( $total_bytes > Moltex_Exporter_Artifact_Registry::MAX_TOTAL_BYTES ) {
			$errors[] = 'ZIP exceeds the uncompressed byte limit.';
		}

		return $entries;
	}

	private function validate_manifest_schema( ZipArchive $zip, array $entries, array $manifest, array &$errors ) {
		$schema_path = 'schemas/bundle.schema.json';
		if ( ! isset( $entries[ $schema_path ] ) ) {
			$errors[] = 'Bundle schema is missing.';
			return;
		}
		$schema = $this->decode_json_entry( $zip, $entries[ $schema_path ]['index'], $schema_path, $errors );
		if ( ! is_array( $schema ) ) {
			return;
		}
		foreach ( $this->schema_validator->validate( $manifest, $schema ) as $schema_error ) {
			$errors[] = 'bundle.json: ' . $schema_error;
		}
	}

	private function validate_inventory( ZipArchive $zip, array $entries, array $manifest, array &$errors ) {
		if ( empty( $manifest['artifacts'] ) || ! is_array( $manifest['artifacts'] ) ) {
			$errors[] = 'Manifest artifact inventory is empty.';
			return;
		}

		$declared = array();
		foreach ( $manifest['artifacts'] as $artifact ) {
			if ( ! is_array( $artifact ) || empty( $artifact['path'] ) ) {
				$errors[] = 'Manifest contains an invalid artifact entry.';
				continue;
			}
			try {
				$path = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $artifact['path'] );
			} catch ( InvalidArgumentException $exception ) {
				$errors[] = 'Manifest contains an unsafe artifact path.';
				continue;
			}
			$key = strtolower( $path );
			if ( isset( $declared[ $key ] ) ) {
				$errors[] = 'Manifest contains a duplicate artifact path: ' . $path . '.';
				continue;
			}
			$declared[ $key ] = true;

			if ( ! isset( $entries[ $path ] ) ) {
				$errors[] = 'Manifest artifact is missing from ZIP: ' . $path . '.';
				continue;
			}
			$content = $zip->getFromIndex( $entries[ $path ]['index'] );
			if ( false === $content ) {
				$errors[] = 'Artifact cannot be read: ' . $path . '.';
				continue;
			}
			if ( ! isset( $artifact['bytes'] ) || (int) $artifact['bytes'] !== strlen( $content ) ) {
				$errors[] = 'Artifact byte size mismatch: ' . $path . '.';
			}
			if ( empty( $artifact['sha256'] ) || ! hash_equals( strtolower( $artifact['sha256'] ), hash( 'sha256', $content ) ) ) {
				$errors[] = 'Artifact checksum mismatch: ' . $path . '.';
			}

			$definition = $this->registry->get_definition( $path );
			if ( ! $definition ) {
				$errors[] = 'Artifact is not declared by the contract registry: ' . $path . '.';
				continue;
			}
			if ( ! array_key_exists( 'required', $artifact ) || (bool) $artifact['required'] !== (bool) $definition['required'] ) {
				$errors[] = 'Artifact required flag disagrees with the registry: ' . $path . '.';
			}

			if ( ! empty( $artifact['schema'] ) ) {
				$this->validate_artifact_schema( $zip, $entries, $path, $content, $artifact['schema'], $errors );
			}
		}

		foreach ( $entries as $path => $entry ) {
			if ( 'bundle.json' === $path ) {
				continue;
			}
			if ( ! isset( $declared[ strtolower( $path ) ] ) ) {
				$errors[] = 'ZIP contains an unlisted artifact: ' . $path . '.';
			}
		}

		foreach ( $this->registry->get_required_paths( false ) as $required_path ) {
			if ( ! isset( $declared[ strtolower( $required_path ) ] ) ) {
				$errors[] = 'Required artifact is absent from the manifest: ' . $required_path . '.';
			}
		}
	}

	private function validate_artifact_schema( ZipArchive $zip, array $entries, $path, $content, $schema_path, array &$errors ) {
		try {
			$schema_path = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $schema_path );
		} catch ( InvalidArgumentException $exception ) {
			$errors[] = 'Artifact schema path is unsafe: ' . $path . '.';
			return;
		}
		if ( ! isset( $entries[ $schema_path ] ) ) {
			$errors[] = 'Artifact schema is missing for ' . $path . ': ' . $schema_path . '.';
			return;
		}
		$data = json_decode( $content, true );
		$data_json_error = json_last_error();
		$schema = $this->decode_json_entry( $zip, $entries[ $schema_path ]['index'], $schema_path, $errors );
		if ( JSON_ERROR_NONE !== $data_json_error ) {
			$errors[] = 'Artifact is not valid JSON: ' . $path . '.';
			return;
		}
		if ( ! is_array( $schema ) ) {
			return;
		}
		foreach ( $this->schema_validator->validate( $data, $schema ) as $schema_error ) {
			$errors[] = $path . ': ' . $schema_error;
		}
	}

	private function validate_bundle_identity( array $manifest, array &$errors ) {
		if ( empty( $manifest['bundle_id'] ) ) {
			return;
		}
		$identity = $manifest;
		unset( $identity['bundle_id'], $identity['created_at'] );
		$expected = 'sha256:' . hash( 'sha256', $this->encode_canonical( $identity ) );
		if ( ! hash_equals( strtolower( $manifest['bundle_id'] ), $expected ) ) {
			$errors[] = 'bundle_id does not match the normalized manifest.';
		}
	}

	private function validate_completeness( ZipArchive $zip, array $entries, array $manifest, array &$errors ) {
		if ( isset( $manifest['mode'] ) && 'complete' === $manifest['mode'] && empty( $manifest['complete'] ) ) {
			$errors[] = 'A complete-mode bundle cannot declare incomplete content.';
		}

		if ( ! isset( $entries['export_completeness.json'] ) ) {
			return;
		}
		$completeness = $this->decode_json_entry( $zip, $entries['export_completeness.json']['index'], 'export_completeness.json', $errors );
		if ( ! is_array( $completeness ) ) {
			return;
		}
		if ( isset( $completeness['complete'] ) && (bool) $completeness['complete'] !== ! empty( $manifest['complete'] ) ) {
			$errors[] = 'Manifest completeness disagrees with export_completeness.json.';
		}
		if ( isset( $completeness['post_types'] ) && isset( $manifest['counts'] ) && $completeness['post_types'] !== $manifest['counts'] ) {
			$errors[] = 'Manifest counts disagree with export_completeness.json.';
		}

		if ( isset( $completeness['post_types'] ) && is_array( $completeness['post_types'] ) ) {
			foreach ( $completeness['post_types'] as $post_type => $counts ) {
				if ( ! is_array( $counts ) ) {
					continue;
				}
				$discovered = isset( $counts['discovered'] ) ? (int) $counts['discovered'] : 0;
				$exported = isset( $counts['exported'] ) ? (int) $counts['exported'] : 0;
				$excluded = isset( $counts['excluded'] ) ? (int) $counts['excluded'] : 0;
				$failed = isset( $counts['failed'] ) ? (int) $counts['failed'] : 0;
				if ( $discovered !== $exported + $excluded + $failed ) {
					$errors[] = 'Content counts do not reconcile for post type: ' . $post_type . '.';
				}
			}
		}

		$excluded_statuses = isset( $manifest['privacy']['excluded_statuses'] ) && is_array( $manifest['privacy']['excluded_statuses'] )
			? $manifest['privacy']['excluded_statuses']
			: array();
		$private_included = ! empty( $manifest['privacy']['private_content_included'] );
		if ( $private_included === in_array( 'private', $excluded_statuses, true ) ) {
			$errors[] = 'Private-content privacy metadata is contradictory.';
		}
	}

	private function decode_json_entry( ZipArchive $zip, $index, $path, array &$errors ) {
		$content = $zip->getFromIndex( $index );
		if ( false === $content ) {
			$errors[] = 'JSON entry cannot be read: ' . $path . '.';
			return null;
		}
		$data = json_decode( $content, true );
		if ( JSON_ERROR_NONE !== json_last_error() ) {
			$errors[] = 'Malformed JSON in ' . $path . ': ' . json_last_error_msg() . '.';
			return null;
		}
		return $data;
	}

	private function is_symlink( ZipArchive $zip, $index ) {
		$opsys = 0;
		$attributes = 0;
		if ( ! $zip->getExternalAttributesIndex( $index, $opsys, $attributes ) ) {
			return false;
		}
		$mode = ( $attributes >> 16 ) & 0xF000;
		return 0xA000 === $mode;
	}

	private function encode_canonical( $value ) {
		return json_encode( $this->canonicalize( $value ), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
	}

	private function canonicalize( $value ) {
		if ( ! is_array( $value ) ) {
			return $value;
		}

		$is_list = array() === $value || array_keys( $value ) === range( 0, count( $value ) - 1 );
		if ( ! $is_list ) {
			ksort( $value, SORT_STRING );
		}
		foreach ( $value as $key => $item ) {
			$value[ $key ] = $this->canonicalize( $item );
		}
		return $value;
	}

	private function result( $valid, array $errors, array $warnings, $bundle_id, $artifact_count, $complete_migration_eligible = false ) {
		return array(
			'valid'          => (bool) $valid,
			'contract'       => Moltex_Exporter_Artifact_Registry::CONTRACT_VERSION,
			'bundle_id'      => $bundle_id,
			'complete_migration_eligible' => (bool) $complete_migration_eligible,
			'artifact_count' => (int) $artifact_count,
			'errors'         => array_values( array_unique( $errors ) ),
			'warnings'       => array_values( array_unique( $warnings ) ),
		);
	}
}
