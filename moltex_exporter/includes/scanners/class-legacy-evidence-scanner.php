<?php
/**
 * Bounded observation index for inactive, missing, and legacy plugin evidence.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

require_once dirname( __DIR__ ) . '/class-plugin-signature-registry.php';

/**
 * Builds source observations without loading inactive plugin code.
 */
class Moltex_Exporter_Legacy_Evidence_Scanner extends Moltex_Exporter_Scanner_Base {

	const MAX_ENTRIES = 5000;
	const MAX_REFERENCES_PER_ENTRY = 100;
	const MAX_REACHABLE_ROWS = 500;
	const MAX_UNKNOWN_SAMPLE_ROWS = 50;

	private $signatures;
	private $plugin_status = array();
	private $public_ids = array();
	private $content_paths = array();

	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->signatures = new Moltex_Exporter_Plugin_Signature_Registry();
	}

	/**
	 * Build the versioned index and deferred payload write requests.
	 *
	 * @return array
	 */
	public function scan() {
		$this->build_plugin_status();
		$content = $this->content_items();
		$this->index_content_paths( $content );

		$entries = array_merge(
			$this->postmeta_entries( $content ),
			$this->shortcode_entries( $content ),
			$this->block_entries( $content ),
			$this->custom_table_entries()
		);
		usort( $entries, function( $left, $right ) {
			return strcmp( $left['evidence_id'], $right['evidence_id'] );
		} );
		if ( count( $entries ) > self::MAX_ENTRIES ) {
			$entries = array_slice( $entries, 0, self::MAX_ENTRIES );
			$this->log_warning( 'legacy_evidence', 'Legacy evidence index reached its bounded entry limit.' );
		}

		$payloads = array();
		foreach ( $entries as &$entry ) {
			if ( isset( $entry['_payload'] ) ) {
				$payloads[] = array(
					'evidence_id' => $entry['evidence_id'],
					'path' => $entry['payload']['artifact'],
					'data' => $entry['_payload'],
				);
				unset( $entry['_payload'] );
			}
		}
		unset( $entry );

		return array(
			'index' => array(
				'schema_version' => 1,
				'limits' => array(
					'max_entries' => self::MAX_ENTRIES,
					'max_references_per_entry' => self::MAX_REFERENCES_PER_ENTRY,
					'max_reachable_rows_per_table' => self::MAX_REACHABLE_ROWS,
				),
				'plugin_inventory' => $this->plugin_inventory(),
				'summary' => $this->summarize( $entries ),
				'entries' => $entries,
			),
			'payloads' => $payloads,
		);
	}

	private function build_plugin_status() {
		$plugins = isset( $this->context['plugins']['plugins_list']['plugins'] ) && is_array( $this->context['plugins']['plugins_list']['plugins'] )
			? $this->context['plugins']['plugins_list']['plugins']
			: array();
		foreach ( $plugins as $plugin ) {
			if ( ! is_array( $plugin ) || empty( $plugin['slug'] ) ) {
				continue;
			}
			$family = $this->signatures->family_for_slug( $plugin['slug'] );
			$family = $family ?: strtolower( (string) $plugin['slug'] );
			$status = ! empty( $plugin['active'] ) ? 'active' : 'inactive';
			if ( ! isset( $this->plugin_status[ $family ] ) || 'active' === $status ) {
				$this->plugin_status[ $family ] = $status;
			}
		}
	}

	private function plugin_inventory() {
		$inventory = array();
		foreach ( $this->plugin_status as $family => $status ) {
			$inventory[] = array( 'source_plugin' => $family, 'status' => $status );
		}
		usort( $inventory, function( $left, $right ) {
			return strcmp( $left['source_plugin'], $right['source_plugin'] );
		} );
		return $inventory;
	}

	private function plugin_status_for( $family ) {
		if ( 'unknown' === $family ) {
			return 'unknown';
		}
		return isset( $this->plugin_status[ $family ] ) ? $this->plugin_status[ $family ] : 'missing';
	}

	private function content_items() {
		$content = isset( $this->context['content'] ) && is_array( $this->context['content'] ) ? $this->context['content'] : array();
		$items = array();
		foreach ( array( 'posts', 'pages' ) as $group ) {
			if ( ! empty( $content[ $group ] ) && is_array( $content[ $group ] ) ) {
				$items = array_merge( $items, $content[ $group ] );
			}
		}
		if ( ! empty( $content['custom_post_types'] ) && is_array( $content['custom_post_types'] ) ) {
			foreach ( $content['custom_post_types'] as $values ) {
				if ( is_array( $values ) ) {
					$items = array_merge( $items, $values );
				}
			}
		}
		return array_values( array_filter( $items, 'is_array' ) );
	}

	private function index_content_paths( $items ) {
		$used = array();
		foreach ( $items as $item ) {
			$type = isset( $item['type'] ) ? sanitize_file_name( (string) $item['type'] ) : 'unknown';
			$base = ! empty( $item['slug'] ) ? sanitize_file_name( (string) $item['slug'] ) : '';
			if ( '' === $base ) {
				$base = ! empty( $item['id'] ) ? 'item-' . (int) $item['id'] : 'content-item';
			}
			$filename = $base . '.json';
			if ( isset( $used[ $type ][ $filename ] ) ) {
				$filename = $base . '-' . ( ! empty( $item['id'] ) ? (int) $item['id'] : count( $used[ $type ] ) + 1 ) . '.json';
			}
			$used[ $type ][ $filename ] = true;
			$id = isset( $item['id'] ) ? (string) $item['id'] : $type . ':' . $base;
			$this->content_paths[ $id ] = 'content/' . $type . '/' . $filename;
			$this->public_ids[ $id ] = true;
		}
	}

	private function postmeta_entries( $items ) {
		$groups = array();
		foreach ( $items as $item ) {
			$meta = isset( $item['postmeta'] ) && is_array( $item['postmeta'] ) ? $item['postmeta'] : array();
			$id = isset( $item['id'] ) ? (string) $item['id'] : '';
			$type = isset( $item['type'] ) ? (string) $item['type'] : 'unknown';
			foreach ( $meta as $key => $value ) {
				if ( Moltex_Exporter_Security_Filters::is_excluded_export_meta_key( $key ) ) {
					continue;
				}
				if ( 0 === strpos( (string) $key, '_' ) && is_string( $value ) && 0 === strpos( $value, 'field_' ) ) {
					continue;
				}
				$ownership = $this->signatures->resolve_meta( $key );
				$acf_key = '_' . ltrim( (string) $key, '_' );
				if ( isset( $meta[ $acf_key ] ) && is_string( $meta[ $acf_key ] ) && 0 === strpos( $meta[ $acf_key ], 'field_' ) ) {
					$ownership = array( 'source_plugin' => 'advanced-custom-fields', 'ownership_confidence' => 'high' );
				}
				$group_key = $type . "\0" . $key;
				if ( ! isset( $groups[ $group_key ] ) ) {
					$groups[ $group_key ] = array(
						'post_type' => $type,
						'field_name' => (string) $key,
						'ownership' => $ownership,
						'references' => array(),
						'lineage' => array(),
					);
				}
				$path = isset( $this->content_paths[ $id ] ) ? $this->content_paths[ $id ] : 'content/' . sanitize_file_name( $type ) . '/unknown.json';
				$groups[ $group_key ]['references'][] = $path . '#/postmeta/' . $this->pointer_token( $key );
				$groups[ $group_key ]['lineage'][] = 'wp_postmeta:post_id=' . $id . ',meta_key=' . $key;
			}
		}

		$entries = array();
		foreach ( $groups as $group ) {
			$owner = $group['ownership']['source_plugin'];
			$entries[] = $this->entry(
				'postmeta_field',
				$owner,
				$group['ownership']['ownership_confidence'],
				array( 'post_type' => $group['post_type'], 'field_name' => $group['field_name'] ),
				'referenced',
				count( $group['references'] ),
				$group['references'],
				array(
					'status' => 'omitted',
					'method' => 'none',
					'artifact' => null,
					'row_count' => count( $group['references'] ),
					'reason' => 'Values remain represented in referenced public content artifacts.',
				),
				$group['lineage']
			);
		}
		return $entries;
	}

	private function shortcode_entries( $items ) {
		$groups = array();
		foreach ( $items as $item ) {
			$html = isset( $item['raw_html'] ) ? (string) $item['raw_html'] : '';
			if ( ! preg_match_all( '/\[(?!\/|\[)([A-Za-z][A-Za-z0-9_-]*)(?:\s[^\]]*)?\]/', $html, $matches ) ) {
				continue;
			}
			$id = isset( $item['id'] ) ? (string) $item['id'] : '';
			foreach ( $matches[1] as $tag ) {
				$tag = strtolower( (string) $tag );
				if ( in_array( $tag, array( 'caption', 'gallery', 'playlist', 'audio', 'video', 'embed' ), true ) ) {
					continue;
				}
				$groups[ $tag ]['count'] = isset( $groups[ $tag ]['count'] ) ? $groups[ $tag ]['count'] + 1 : 1;
				$groups[ $tag ]['references'][] = $this->content_paths[ $id ] . '#/raw_html';
			}
		}
		$entries = array();
		foreach ( $groups as $tag => $group ) {
			$ownership = $this->signatures->resolve_shortcode( $tag );
			$entries[] = $this->entry(
				'shortcode', $ownership['source_plugin'], $ownership['ownership_confidence'],
				array( 'tag' => $tag ), 'referenced', $group['count'], $group['references'],
				array( 'status' => 'omitted', 'method' => 'none', 'artifact' => null, 'row_count' => $group['count'], 'reason' => 'Raw shortcode markup remains in public content artifacts.' ),
				array( 'post_content:shortcode=' . $tag )
			);
		}
		return $entries;
	}

	private function block_entries( $items ) {
		$groups = array();
		foreach ( $items as $item ) {
			$html = isset( $item['raw_html'] ) ? (string) $item['raw_html'] : '';
			if ( ! preg_match_all( '/<!--\s+wp:([a-z0-9_-]+\/[a-z0-9_-]+)(?:\s+.*?)?\s*(\/)?-->/is', $html, $matches ) ) {
				continue;
			}
			$id = isset( $item['id'] ) ? (string) $item['id'] : '';
			foreach ( $matches[1] as $name ) {
				$name = strtolower( (string) $name );
				if ( 0 === strpos( $name, 'core/' ) ) {
					continue;
				}
				$groups[ $name ]['count'] = isset( $groups[ $name ]['count'] ) ? $groups[ $name ]['count'] + 1 : 1;
				$groups[ $name ]['references'][] = $this->content_paths[ $id ] . '#/raw_html';
			}
		}
		$entries = array();
		foreach ( $groups as $name => $group ) {
			$ownership = $this->signatures->resolve_block( $name );
			$entries[] = $this->entry(
				'block', $ownership['source_plugin'], $ownership['ownership_confidence'],
				array( 'name' => $name ), 'referenced', $group['count'], $group['references'],
				array( 'status' => 'omitted', 'method' => 'none', 'artifact' => null, 'row_count' => $group['count'], 'reason' => 'Raw block markup remains in public content artifacts.' ),
				array( 'post_content:block=' . $name )
			);
		}
		return $entries;
	}

	private function custom_table_entries() {
		$manifest = isset( $this->context['database']['custom_tables_manifest'] ) && is_array( $this->context['database']['custom_tables_manifest'] )
			? $this->context['database']['custom_tables_manifest']
			: array();
		$existing_exports = isset( $this->context['plugin_table_exports'] ) && is_array( $this->context['plugin_table_exports'] )
			? $this->context['plugin_table_exports']
			: array();
		$exports_by_table = array();
		foreach ( $existing_exports as $export ) {
			if ( is_array( $export ) && ! empty( $export['table_name'] ) ) {
				$exports_by_table[ $export['table_name'] ] = $export;
			}
		}

		$entries = array();
		foreach ( $manifest as $table => $info ) {
			if ( ! is_array( $info ) || ! preg_match( '/^[A-Za-z0-9_]+$/', (string) $table ) ) {
				continue;
			}
			$suffix = $this->table_suffix( $table );
			$ownership = $this->signatures->resolve_table( $suffix );
			$columns = isset( $info['columns'] ) && is_array( $info['columns'] ) ? $info['columns'] : array();
			$relationship_columns = array();
			$primary_key = 'id';
			foreach ( $columns as $column ) {
				$name = is_array( $column ) && isset( $column['name'] ) ? (string) $column['name'] : '';
				if ( ! preg_match( '/^[A-Za-z0-9_]+$/', $name ) ) {
					continue;
				}
				if ( in_array( strtolower( $name ), array( 'post_id', 'object_id', 'item_id' ), true ) ) {
					$relationship_columns[] = $name;
				}
				if ( isset( $column['key'] ) && 'PRI' === $column['key'] ) {
					$primary_key = $name;
				}
			}

			$reachable = array();
			$reachable_count = 0;
			if ( empty( $info['is_sensitive'] ) && ! empty( $relationship_columns ) ) {
				if ( isset( $exports_by_table[ $table ]['rows'] ) ) {
					foreach ( $exports_by_table[ $table ]['rows'] as $row ) {
						if ( $this->row_is_public( $row, $relationship_columns ) ) {
							$reachable[] = $row;
						}
					}
					$reachable_count = count( $reachable );
				} else {
					list( $reachable_count, $reachable ) = $this->query_reachable_rows( $table, $relationship_columns, $primary_key );
				}
			}

			$status = 'omitted';
			$method = 'none';
			$artifact = null;
			$payload_rows = array();
			$reason = ! empty( $info['is_sensitive'] ) ? 'Sensitive table payload is excluded.' : 'No rows are connected to exported public objects.';
			if ( $reachable_count > self::MAX_REACHABLE_ROWS ) {
				$status = 'deferred';
				$method = 'targeted-export';
				$reason = 'Reachable rows exceed the initial-bundle limit.';
			} elseif ( $reachable_count > 0 ) {
				$status = 'unknown' === $ownership['source_plugin'] ? 'sampled' : 'included';
				$payload_rows = array_slice( $reachable, 0, 'sampled' === $status ? self::MAX_UNKNOWN_SAMPLE_ROWS : self::MAX_REACHABLE_ROWS );
				$artifact = 'legacy/tables/' . sha1( (string) $table ) . '.json';
				$method = 'bundle';
				$reason = 'Only rows connected to exported public objects are bundled.';
			}

			$payload = array(
				'status' => $status,
				'method' => $method,
				'artifact' => $artifact,
				'row_count' => (int) $reachable_count,
				'excluded_row_count' => max( 0, (int) $info['row_count'] - (int) $reachable_count ),
				'reason' => $reason,
			);
			$entry = $this->entry(
				'custom_table', $ownership['source_plugin'], $ownership['ownership_confidence'],
				array(
					'table_name' => (string) $table,
					'schema_sha256' => hash( 'sha256', wp_json_encode( $columns ) ),
					'relationship_columns' => array_values( array_unique( $relationship_columns ) ),
				),
				$reachable_count > 0 ? 'referenced' : 'unreferenced',
				$reachable_count,
				array(),
				$payload,
				array( 'database.custom_tables_manifest:' . $table )
			);
			if ( ! empty( $payload_rows ) ) {
				$entry['_payload'] = array(
					'schema_version' => 1,
					'evidence_id' => $entry['evidence_id'],
					'table_name' => (string) $table,
					'complete' => 'included' === $status,
					'rows' => $payload_rows,
				);
			}
			$entries[] = $entry;
		}
		return $entries;
	}

	private function query_reachable_rows( $table, $columns, $primary_key ) {
		global $wpdb;
		if ( ! is_object( $wpdb ) || empty( $this->public_ids ) ) {
			return array( 0, array() );
		}
		$ids = array_map( 'intval', array_keys( $this->public_ids ) );
		$ids = array_values( array_filter( array_unique( $ids ) ) );
		if ( empty( $ids ) ) {
			return array( 0, array() );
		}
		$clauses = array();
		$args = array();
		$placeholders = implode( ',', array_fill( 0, count( $ids ), '%d' ) );
		foreach ( $columns as $column ) {
			$clauses[] = "`{$column}` IN ({$placeholders})";
			$args = array_merge( $args, $ids );
		}
		$where = implode( ' OR ', $clauses );
		$count_sql = $wpdb->prepare( "SELECT COUNT(*) FROM `{$table}` WHERE {$where}", $args );
		$count = (int) $wpdb->get_var( $count_sql );
		if ( 0 === $count ) {
			return array( 0, array() );
		}
		$args[] = self::MAX_REACHABLE_ROWS;
		$rows_sql = $wpdb->prepare( "SELECT * FROM `{$table}` WHERE {$where} ORDER BY `{$primary_key}` ASC LIMIT %d", $args );
		$rows = $wpdb->get_results( $rows_sql, ARRAY_A );
		$filtered = array();
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			$filtered[] = Moltex_Exporter_Security_Filters::sanitize_export_data( $row );
		}
		return array( $count, $filtered );
	}

	private function row_is_public( $row, $columns ) {
		if ( ! is_array( $row ) ) {
			return false;
		}
		foreach ( $columns as $column ) {
			if ( isset( $row[ $column ] ) && isset( $this->public_ids[ (string) $row[ $column ] ] ) ) {
				return true;
			}
		}
		return false;
	}

	private function table_suffix( $table ) {
		global $wpdb;
		$prefix = is_object( $wpdb ) && isset( $wpdb->prefix ) ? (string) $wpdb->prefix : '';
		return $prefix && 0 === strpos( $table, $prefix ) ? substr( $table, strlen( $prefix ) ) : $table;
	}

	private function entry( $type, $owner, $confidence, $identity, $relationship, $reference_count, $references, $payload, $lineage ) {
		ksort( $identity, SORT_STRING );
		$id_source = $type . "\0" . $owner . "\0" . wp_json_encode( $identity );
		$references = array_values( array_unique( array_slice( $references, 0, self::MAX_REFERENCES_PER_ENTRY ) ) );
		$lineage = array_values( array_unique( array_slice( $lineage, 0, self::MAX_REFERENCES_PER_ENTRY ) ) );
		return array(
			'evidence_id' => 'legacy:' . $type . ':' . hash( 'sha256', $id_source ),
			'artifact_type' => $type,
			'source_plugin' => $owner,
			'ownership_confidence' => $confidence,
			'plugin_status' => $this->plugin_status_for( $owner ),
			'source_identity' => $identity,
			'relationship_status' => $relationship,
			'public_reference_count' => (int) $reference_count,
			'reference_evidence' => $references,
			'payload' => $payload,
			'source_lineage' => $lineage,
		);
	}

	private function summarize( $entries ) {
		$summary = array(
			'total' => count( $entries ),
			'referenced' => 0,
			'unreferenced' => 0,
			'unknown_relationship' => 0,
			'included_payloads' => 0,
			'sampled_payloads' => 0,
			'deferred_payloads' => 0,
			'omitted_payloads' => 0,
		);
		foreach ( $entries as $entry ) {
			$key = 'unknown' === $entry['relationship_status'] ? 'unknown_relationship' : $entry['relationship_status'];
			$summary[ $key ]++;
			$payload_key = $entry['payload']['status'] . '_payloads';
			if ( isset( $summary[ $payload_key ] ) ) {
				$summary[ $payload_key ]++;
			}
		}
		return $summary;
	}

	private function pointer_token( $value ) {
		return str_replace( array( '~', '/' ), array( '~0', '~1' ), (string) $value );
	}
}
