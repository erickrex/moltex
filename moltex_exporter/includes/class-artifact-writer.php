<?php
/**
 * Validated, atomic artifact writer for moltex-export/1.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

require_once __DIR__ . '/class-privacy-scanner.php';

/**
 * Contract write failure with producer and path context.
 */
class Moltex_Exporter_Contract_Exception extends RuntimeException {
}

/**
 * Writes contract JSON and produces the deterministic bundle manifest.
 */
class Moltex_Exporter_Artifact_Writer {

	private $export_dir;
	private $registry;
	private $validator;
	private $schema_source_dir;
	private $written_paths = array();

	public function __construct( $export_dir, Moltex_Exporter_Artifact_Registry $registry = null, Moltex_Exporter_Schema_Validator $validator = null ) {
		$this->export_dir = rtrim( str_replace( '\\', '/', $export_dir ), '/' ) . '/';
		$this->registry = $registry ?: new Moltex_Exporter_Artifact_Registry();
		$this->validator = $validator ?: new Moltex_Exporter_Schema_Validator();
		$this->schema_source_dir = dirname( __DIR__ ) . '/schemas/moltex-export-1/';
	}

	/**
	 * Write a declared JSON artifact.
	 *
	 * @param string $path Relative artifact path.
	 * @param mixed  $data JSON-compatible data.
	 * @param string $producer Producer name.
	 * @return array Write receipt.
	 */
	public function write_json( $path, $data, $producer = '' ) {
		$path = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $path );
		$definition = $this->registry->get_definition( $path );
		if ( ! $definition ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Artifact path is not declared.' ) );
		}

		if ( isset( $this->written_paths[ strtolower( $path ) ] ) ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Duplicate normalized artifact path.' ) );
		}

		if ( ! empty( $definition['schema_versioned'] ) && is_array( $data ) && ! isset( $data['schema_version'] ) ) {
			$data = array_merge( array( 'schema_version' => 1 ), $data );
		}

		$data = $this->canonicalize( $data );
		if ( ! empty( $definition['schema'] ) ) {
			$schema_path = $this->source_schema_path( $definition['schema'] );
			$errors = $this->validator->validate_file( $data, $schema_path );
			if ( ! empty( $errors ) ) {
				throw new Moltex_Exporter_Contract_Exception(
					$this->message( $producer, $path, 'Schema validation failed: ' . implode( ' ', $errors ) )
				);
			}
		}

		$options = JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE;
		$json = function_exists( 'wp_json_encode' ) ? wp_json_encode( $data, $options ) : json_encode( $data, $options );
		if ( false === $json ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'JSON encoding failed: ' . json_last_error_msg() ) );
		}
		$json .= "\n";

		if ( strlen( $json ) > (int) $definition['max_bytes'] ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Artifact exceeds its declared byte limit.' ) );
		}

		$this->write_atomic( $path, $json, $producer );
		$this->written_paths[ strtolower( $path ) ] = true;

		return $this->receipt( $path, $json, $definition, $producer );
	}

	/**
	 * Copy checked-in contract schemas into the bundle through the writer.
	 */
	public function write_schema_artifacts() {
		foreach ( Moltex_Exporter_Artifact_Registry::get_schema_filenames() as $filename ) {
			$source_path = $this->schema_source_dir . $filename;
			if ( ! is_readable( $source_path ) ) {
				throw new Moltex_Exporter_Contract_Exception( 'Contract schema is unavailable: ' . $filename );
			}
			$data = json_decode( file_get_contents( $source_path ), true );
			if ( ! is_array( $data ) || JSON_ERROR_NONE !== json_last_error() ) {
				throw new Moltex_Exporter_Contract_Exception( 'Contract schema is invalid JSON: ' . $filename );
			}
			$this->write_json( 'schemas/' . $filename, $data, 'contract' );
		}
	}

	/**
	 * Inventory all artifacts, enforce required paths, and write bundle.json.
	 *
	 * @param array $metadata Export mode, counts, privacy, and timestamp.
	 * @return array Bundle manifest.
	 */
	public function finalize_bundle( array $metadata ) {
		$privacy_receipt = ( new Moltex_Exporter_Privacy_Scanner( $this->export_dir ) )->scan();
		$privacy_artifact = $this->write_json( 'privacy-scan.json', $privacy_receipt, 'privacy' );
		$privacy = isset( $metadata['privacy'] ) && is_array( $metadata['privacy'] ) ? $metadata['privacy'] : array();
		$privacy['secret_scan'] = 'pass';
		$privacy['secret_scan_receipt'] = array(
			'path'   => $privacy_artifact['path'],
			'sha256' => $privacy_artifact['sha256'],
		);
		$metadata['privacy'] = $privacy;
		$this->write_schema_artifacts();
		$artifacts = $this->inventory_artifacts();
		$paths = array_column( $artifacts, 'path' );

		foreach ( $this->registry->get_required_paths( false ) as $required_path ) {
			if ( ! in_array( $required_path, $paths, true ) ) {
				throw new Moltex_Exporter_Contract_Exception( 'Required artifact is missing: ' . $required_path );
			}
		}

		$manifest = array(
			'schema'            => Moltex_Exporter_Artifact_Registry::CONTRACT_VERSION,
			'manifest_version'  => 1,
			'created_at'        => isset( $metadata['created_at'] ) ? $metadata['created_at'] : gmdate( 'c' ),
			'exporter_version'  => isset( $metadata['exporter_version'] ) ? $metadata['exporter_version'] : 'unknown',
			'mode'              => isset( $metadata['mode'] ) ? $metadata['mode'] : 'complete',
			'site_origin'       => isset( $metadata['site_origin'] ) ? $metadata['site_origin'] : '',
			'site_identity'     => isset( $metadata['site_identity'] ) ? $metadata['site_identity'] : null,
			'complete'          => ! empty( $metadata['complete'] ),
			'privacy'           => isset( $metadata['privacy'] ) ? $metadata['privacy'] : array(),
			'counts'            => isset( $metadata['counts'] ) ? $metadata['counts'] : array(),
			'artifacts'         => $artifacts,
			'artifact_registry' => $this->registry->to_manifest_registry(),
		);

		$identity = $manifest;
		unset( $identity['created_at'] );
		$manifest['bundle_id'] = 'sha256:' . hash( 'sha256', $this->encode_canonical( $identity ) );
		$this->write_json( 'bundle.json', $manifest, 'exporter' );

		return $manifest;
	}

	/**
	 * Return a deterministic inventory of existing files except bundle.json.
	 *
	 * @return array
	 */
	public function inventory_artifacts() {
		$root = realpath( $this->export_dir );
		if ( false === $root ) {
			throw new Moltex_Exporter_Contract_Exception( 'Export directory does not exist.' );
		}

		$artifacts = array();
		$seen = array();
		$total_bytes = 0;
		$iterator = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator( $root, FilesystemIterator::SKIP_DOTS )
		);

		foreach ( $iterator as $file ) {
			if ( ! $file->isFile() || $file->isLink() ) {
				continue;
			}
			$relative = substr( str_replace( '\\', '/', $file->getPathname() ), strlen( str_replace( '\\', '/', $root ) ) + 1 );
			$relative = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $relative );
			if ( 'bundle.json' === $relative ) {
				continue;
			}
			$key = strtolower( $relative );
			if ( isset( $seen[ $key ] ) ) {
				throw new Moltex_Exporter_Contract_Exception( 'Duplicate normalized artifact path: ' . $relative );
			}
			$seen[ $key ] = true;

			$definition = $this->registry->get_definition( $relative );
			if ( ! $definition ) {
				throw new Moltex_Exporter_Contract_Exception( 'Artifact is not declared: ' . $relative );
			}
			$bytes = $file->getSize();
			if ( $bytes > (int) $definition['max_bytes'] ) {
				throw new Moltex_Exporter_Contract_Exception( 'Artifact exceeds its declared byte limit: ' . $relative );
			}
			$total_bytes += $bytes;

			$artifacts[] = array(
				'path'     => $relative,
				'kind'     => $definition['kind'],
				'producer' => $definition['producer'],
				'required' => (bool) $definition['required'],
				'schema'   => $definition['schema'],
				'bytes'    => $bytes,
				'sha256'   => hash_file( 'sha256', $file->getPathname() ),
			);
		}

		if ( count( $artifacts ) > Moltex_Exporter_Artifact_Registry::MAX_FILE_COUNT ) {
			throw new Moltex_Exporter_Contract_Exception( 'Bundle exceeds the declared artifact count limit.' );
		}
		if ( $total_bytes > Moltex_Exporter_Artifact_Registry::MAX_TOTAL_BYTES ) {
			throw new Moltex_Exporter_Contract_Exception( 'Bundle exceeds the declared uncompressed byte limit.' );
		}

		usort( $artifacts, function( $left, $right ) { return strcmp( $left['path'], $right['path'] ); } );
		return $artifacts;
	}

	private function source_schema_path( $relative_schema_path ) {
		return $this->schema_source_dir . basename( $relative_schema_path );
	}

	private function write_atomic( $path, $content, $producer ) {
		$target = $this->export_dir . $path;
		$directory = dirname( $target );
		if ( ! is_dir( $directory ) && ! ( function_exists( 'wp_mkdir_p' ) ? wp_mkdir_p( $directory ) : mkdir( $directory, 0755, true ) ) ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Unable to create the artifact directory.' ) );
		}

		$root = realpath( $this->export_dir );
		$real_directory = realpath( $directory );
		if ( false === $root || false === $real_directory || 0 !== strpos( str_replace( '\\', '/', $real_directory ) . '/', str_replace( '\\', '/', $root ) . '/' ) ) {
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Artifact path escapes the export directory.' ) );
		}

		$temp = $target . '.tmp-' . str_replace( '.', '', uniqid( '', true ) );
		$bytes = file_put_contents( $temp, $content, LOCK_EX );
		if ( false === $bytes || $bytes !== strlen( $content ) ) {
			@unlink( $temp );
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Atomic temporary write failed.' ) );
		}

		if ( ! @rename( $temp, $target ) ) {
			@unlink( $temp );
			throw new Moltex_Exporter_Contract_Exception( $this->message( $producer, $path, 'Atomic replace failed.' ) );
		}
		@chmod( $target, 0644 );
	}

	private function receipt( $path, $content, array $definition, $producer ) {
		return array(
			'path'     => $path,
			'kind'     => $definition['kind'],
			'producer' => $producer ?: $definition['producer'],
			'required' => (bool) $definition['required'],
			'schema'   => $definition['schema'],
			'bytes'    => strlen( $content ),
			'sha256'   => hash( 'sha256', $content ),
		);
	}

	private function canonicalize( $value ) {
		if ( ! is_array( $value ) ) {
			return $value;
		}
		if ( $this->is_list( $value ) ) {
			return array_map( array( $this, 'canonicalize' ), $value );
		}
		ksort( $value, SORT_STRING );
		foreach ( $value as $key => $item ) {
			$value[ $key ] = $this->canonicalize( $item );
		}
		return $value;
	}

	private function encode_canonical( $value ) {
		$json = json_encode( $this->canonicalize( $value ), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
		if ( false === $json ) {
			throw new Moltex_Exporter_Contract_Exception( 'Unable to encode bundle identity.' );
		}
		return $json;
	}

	private function is_list( array $value ) {
		return array() === $value || array_keys( $value ) === range( 0, count( $value ) - 1 );
	}

	private function message( $producer, $path, $message ) {
		return sprintf( '[%s] %s: %s', $producer ?: 'unknown', $path, $message );
	}
}
