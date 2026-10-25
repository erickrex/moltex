<?php
/**
 * Content Scanner Class
 *
 * Exports complete or representative content from posts, pages, and custom
 * post types.
 * Parses blocks, generates block usage statistics, and exports content
 * to structured JSON files.
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Content Scanner Class
 */
class Moltex_Exporter_Content_Scanner extends Moltex_Exporter_Scanner_Base {

	/** Maximum representative rendered HTML snapshots per export. */
	const MAX_HTML_SNAPSHOTS = 12;

	/**
	 * Block usage statistics.
	 *
	 * @var array
	 */
	private $block_usage = array();

	/**
	 * Settings for sample limits.
	 *
	 * @var array
	 */
	private $settings = array();

	/** Cached GeoDirectory detail-table lookups keyed by post type. */
	private $geodir_detail_tables = array();

	/** Cached GeoDirectory field definitions keyed by post type. */
	private $geodir_field_definitions = array();

	/** Every row of geodir_custom_fields, as last read (C2 reconciliation). */
	private $geodir_field_rows = null;

	/** Per post type, definition rows without an htmlvar_name. */
	private $geodir_unkeyed_field_rows = array();

	/** Cached GeoDirectory table-existence checks. */
	private $geodir_tables = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->load_settings();
	}

	/**
	 * Load settings from wp_options.
	 */
	private function load_settings() {
		$defaults = array(
			'export_mode' => 'complete',
			'complete_export_max_items' => 5000,
			'include_private_content' => false,
			'max_posts' => 100,
			'max_pages' => 50,
			'max_per_custom_post_type' => 10,
			'html_snapshot_mode' => 'bounded',
			'include_html_snapshots' => true,
		);

		$saved_settings = get_option( 'moltex_settings', array() );
		if ( ! isset( $saved_settings['html_snapshot_mode'] ) && array_key_exists( 'include_html_snapshots', $saved_settings ) ) {
			$saved_settings['html_snapshot_mode'] = $saved_settings['include_html_snapshots'] ? 'bounded' : 'off';
		}
		$this->settings = wp_parse_args( $saved_settings, $defaults );
	}

	/**
	 * Scan and collect content.
	 *
	 * @return array Content data.
	 */
	public function scan() {
		$this->block_usage = array();

		$posts = $this->export_posts();
		$pages = $this->export_pages();
		$cpts  = $this->export_custom_post_types();

		$content_data = array(
			'export_mode'        => $this->get_export_mode(),
			'posts'             => $posts,
			'pages'             => $pages,
			'custom_post_types' => $cpts,
			'block_usage'       => $this->get_block_usage_stats(),
		);
		$geodirectory = $this->get_geodirectory_configuration( array_keys( $cpts ) );
		if ( ! empty( $geodirectory['post_types'] ) ) {
			$content_data['geodirectory'] = $geodirectory;
		}
		$content_data['completeness'] = $this->build_completeness_report( $content_data );
		// The snapshot route planner needs the post-type inventory (S1).
		$content_data['post_type_inventory'] = $this->build_post_type_inventory();
		$this->generate_selected_html_snapshots( $content_data );

		// Surface a warning when the content scanner finds nothing so the
		// empty-content/ issue is visible in the error log.
		$total = count( $posts ) + count( $pages );
		foreach ( $cpts as $items ) {
			$total += is_array( $items ) ? count( $items ) : 0;
		}
		if ( $total === 0 ) {
			$this->log_warning(
				'content',
				'Content scanner returned 0 items (0 posts, 0 pages, 0 CPT items). The content/ directory will be empty.'
			);
		} else {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log(
					sprintf(
						'Moltex Exporter: Content scanner found %d posts, %d pages, %d CPT groups',
						count( $posts ),
						count( $pages ),
						count( $cpts )
					)
				);
			}
		}

		return $content_data;
	}

	/**
	 * Export sample posts.
	 *
	 * @return array Exported posts data.
	 */
	private function export_posts() {
		$limit = $this->get_content_limit( 'post', 'max_posts' );
		
		$args = array(
			'post_type'      => 'post',
			'post_status'    => $this->get_export_statuses(),
			'posts_per_page' => $limit,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'no_found_rows'  => true,
		);

		return $this->query_and_export_content( $args, 'post' );
	}

	/**
	 * Export sample pages.
	 *
	 * @return array Exported pages data.
	 */
	private function export_pages() {
		$limit = $this->get_content_limit( 'page', 'max_pages' );
		
		$args = array(
			'post_type'      => 'page',
			'post_status'    => $this->get_export_statuses(),
			'posts_per_page' => $limit,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'no_found_rows'  => true,
		);

		return $this->query_and_export_content( $args, 'page' );
	}

	/**
	 * Export samples from all custom post types.
	 *
	 * @return array Exported custom post types data.
	 */
	private function export_custom_post_types() {
		$custom_post_types = $this->get_custom_post_types();
		$exported_data = array();

		foreach ( $custom_post_types as $post_type ) {
			$limit = $this->get_content_limit( $post_type, 'max_per_custom_post_type' );
			
			$args = array(
				'post_type'      => $post_type,
				'post_status'    => $this->get_export_statuses(),
				'posts_per_page' => $limit,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'no_found_rows'  => true,
			);

			$exported_data[ $post_type ] = $this->query_and_export_content( $args, $post_type );
		}

		return $exported_data;
	}

	/**
	 * Return the normalized export mode.
	 *
	 * @return string Either complete or discovery.
	 */
	private function get_export_mode() {
		return isset( $this->settings['export_mode'] ) && 'discovery' === $this->settings['export_mode']
			? 'discovery'
			: 'complete';
	}

	/**
	 * Return statuses that are safe for the selected migration export.
	 *
	 * Private content is excluded by default so a public rebuild cannot expose
	 * it accidentally.
	 *
	 * @return array
	 */
	private function get_export_statuses() {
		$status = array( 'publish' );
		if ( ! empty( $this->settings['include_private_content'] ) ) {
			$status[] = 'private';
		}
		return $status;
	}

	/**
	 * Resolve the query limit and enforce the initial basic-site safety ceiling.
	 *
	 * @param string $post_type Post type.
	 * @param string $sample_key Discovery-mode limit setting.
	 * @return int
	 */
	private function get_content_limit( $post_type, $sample_key ) {
		if ( 'discovery' === $this->get_export_mode() ) {
			return max( 1, absint( $this->settings[ $sample_key ] ) );
		}

		$discovered = $this->count_exportable_items( $post_type );
		$ceiling = max( 1, absint( $this->settings['complete_export_max_items'] ) );
		if ( $discovered > $ceiling ) {
			$this->log_warning(
				'content',
				sprintf(
					'Post type %s contains %d exportable items, above the supported complete-export ceiling of %d. The bundle will be marked incomplete.',
					$post_type,
					$discovered,
					$ceiling
				)
			);
			return $ceiling;
		}

		return -1;
	}

	/**
	 * Count exportable content for a post type.
	 *
	 * @param string $post_type Post type.
	 * @return int
	 */
	private function count_exportable_items( $post_type ) {
		$counts = wp_count_posts( $post_type );
		$total = 0;
		foreach ( $this->get_export_statuses() as $status ) {
			$total += isset( $counts->{$status} ) ? (int) $counts->{$status} : 0;
		}
		return $total;
	}

	/**
	 * Build a machine-readable completeness assertion for downstream Codex work.
	 *
	 * @param array $content_data Exported content groups.
	 * @return array
	 */
	private function build_completeness_report( $content_data ) {
		$types = array(
			'post' => isset( $content_data['posts'] ) ? count( $content_data['posts'] ) : 0,
			'page' => isset( $content_data['pages'] ) ? count( $content_data['pages'] ) : 0,
		);
		if ( ! empty( $content_data['custom_post_types'] ) ) {
			foreach ( $content_data['custom_post_types'] as $post_type => $items ) {
				$types[ $post_type ] = is_array( $items ) ? count( $items ) : 0;
			}
		}

		$report = array();
		$complete = 'complete' === $this->get_export_mode();
		foreach ( $types as $post_type => $exported ) {
			$discovered = $this->count_exportable_items( $post_type );
			$is_complete = $exported === $discovered;
			$complete = $complete && $is_complete;
			$report[ $post_type ] = array(
				'discovered' => $discovered,
				'exported'   => $exported,
				'excluded'   => max( 0, $discovered - $exported ),
				'failed'     => 0,
				'complete'   => $is_complete,
			);
		}

		return array(
			'complete' => $complete,
			'post_types' => $report,
			'excluded_statuses' => empty( $this->settings['include_private_content'] ) ? array( 'private', 'draft', 'pending', 'future', 'trash' ) : array( 'draft', 'pending', 'future', 'trash' ),
		);
	}

	/**
	 * Get all custom post types (excluding built-in types).
	 *
	 * @return array Custom post type names.
	 */
	private function get_custom_post_types() {
		$all_post_types = get_post_types( array( 'public' => true ), 'names' );

		// Operator opt-in for non-public types such as wp_story or popup_theme (C8).
		foreach ( Moltex_Exporter_Export_Policy::get( 'include_non_public_post_types' ) as $post_type ) {
			if ( post_type_exists( $post_type ) && ! in_array( $post_type, $all_post_types, true ) ) {
				$all_post_types[] = $post_type;
			}
		}

		// Exclude built-in types
		$exclude = array( 'post', 'page', 'attachment' );

		return array_values( array_diff( $all_post_types, $exclude ) );
	}

	/**
	 * Every registered post type with its counts and why it was or was not exported (C8).
	 *
	 * @return array
	 */
	private function build_post_type_inventory() {
		$exported = array_merge( array( 'post', 'page' ), $this->get_custom_post_types() );
		$opted_in = Moltex_Exporter_Export_Policy::get( 'include_non_public_post_types' );
		$internal = array( 'revision', 'nav_menu_item', 'custom_css', 'customize_changeset', 'oembed_cache', 'user_request', 'wp_block', 'wp_template', 'wp_template_part', 'wp_global_styles', 'wp_navigation', 'wp_font_family', 'wp_font_face' );
		$inventory = array();
		foreach ( (array) get_post_types( array(), 'objects' ) as $name => $object ) {
			$name = is_object( $object ) && isset( $object->name ) ? (string) $object->name : (string) $name;
			$public = is_object( $object ) && ! empty( $object->public );
			$counts = array();
			foreach ( (array) wp_count_posts( $name ) as $status => $count ) {
				if ( (int) $count > 0 ) {
					$counts[ (string) $status ] = (int) $count;
				}
			}
			ksort( $counts, SORT_STRING );
			if ( in_array( $name, $exported, true ) ) {
				$reason = in_array( $name, $opted_in, true ) && ! $public ? 'operator_included' : 'exported';
			} elseif ( 'attachment' === $name ) {
				$reason = 'exported_via_media_map';
			} elseif ( in_array( $name, $internal, true ) ) {
				$reason = 'wordpress_internal';
			} else {
				$reason = $public ? 'not_exported' : 'non_public_not_opted_in';
			}
			$inventory[ $name ] = array(
				'label'    => is_object( $object ) && isset( $object->label ) ? (string) $object->label : $name,
				'public'   => $public,
				'builtin'  => is_object( $object ) && ! empty( $object->_builtin ),
				'counts'   => $counts,
				'exported' => in_array( $reason, array( 'exported', 'operator_included' ), true ),
				'reason'   => $reason,
			);
		}
		ksort( $inventory, SORT_STRING );
		return array( 'schema_version' => 1, 'post_types' => $inventory );
	}

	/**
	 * Query and export content based on WP_Query args.
	 *
	 * @param array  $args WP_Query arguments.
	 * @param string $post_type Post type being queried.
	 * @return array Exported content items.
	 */
	private function query_and_export_content( $args, $post_type ) {
		$query = new WP_Query( $args );
		$exported_items = array();

		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$post = get_post();
				
				$exported_items[] = $this->export_single_content_item( $post );
			}
			wp_reset_postdata();
		}

		return $exported_items;
	}

	/**
	 * Export a single content item to structured format.
	 *
	 * @param WP_Post $post Post object.
	 * @return array Structured content data.
	 */
	private function export_single_content_item( $post ) {
		// Parse blocks from content
		$blocks = parse_blocks( $post->post_content );
		$parsed_blocks = $this->parse_and_track_blocks( $blocks );

		// Get author info
		$author = get_userdata( $post->post_author );
		$author_data = array(
			'display_name' => $author ? $author->display_name : 'Unknown',
		);

		// Get taxonomies
		$taxonomies = $this->get_post_taxonomies( $post );

		// Get featured media
		$featured_media = $this->get_featured_media( $post->ID );

		// Get internal links
		$internal_links = $this->extract_internal_links( $post->post_content );

		// Get legacy permalink
		$legacy_permalink = $this->get_legacy_permalink( $post );

		// Get template
		$template = get_page_template_slug( $post->ID );
		if ( empty( $template ) ) {
			$template = 'default';
		}

		// Get postmeta
		$postmeta = $this->get_post_metadata( $post->ID, $post->post_type );
		$postmeta_diagnostics = $this->extract_nested_postmeta( $postmeta );

		// Build content item
		$content_item = array(
			'type'             => $post->post_type,
			'id'               => $post->ID,
			'slug'             => $post->post_name,
			'status'           => $post->post_status,
			'title'            => $post->post_title,
			'excerpt'          => $post->post_excerpt,
			'author'           => $author_data,
			'date_gmt'         => $post->post_date_gmt,
			'modified_gmt'     => $post->post_modified_gmt,
			'taxonomies'       => $taxonomies,
			'blocks'           => $parsed_blocks,
			'raw_html'         => $post->post_content,
			'featured_media'   => $featured_media,
			'internal_links'   => $internal_links,
			'legacy_permalink' => $legacy_permalink,
			'template'         => $template,
			'postmeta'         => $postmeta,
		);
		if ( ! empty( $postmeta_diagnostics ) ) {
			$content_item['diagnostics']['nested_postmeta'] = $postmeta_diagnostics;
		}
		$search_placements = self::find_search_placements( (string) $post->post_content );
		if ( ! empty( $search_placements ) ) {
			$content_item['search_placements'] = $search_placements;
		}

		// Add GeoDirectory-specific metadata if this is a GeoDirectory CPT
		if ( $this->is_geodirectory_cpt( $post->post_type ) ) {
			$geodir_data = $this->get_geodirectory_metadata( $post );
			if ( ! empty( $geodir_data ) ) {
				$content_item['geodirectory'] = $geodir_data;
			}
		}

		return $content_item;
	}

	/**
	 * Parse blocks and track usage statistics.
	 *
	 * @param array $blocks Parsed blocks from parse_blocks().
	 * @return array Processed blocks with sanitized HTML.
	 */
	private function parse_and_track_blocks( $blocks ) {
		$parsed = array();

		foreach ( $blocks as $block ) {
			// Skip empty blocks
			if ( empty( $block['blockName'] ) ) {
				continue;
			}

			// Track block usage
			if ( ! isset( $this->block_usage[ $block['blockName'] ] ) ) {
				$this->block_usage[ $block['blockName'] ] = 0;
			}
			$this->block_usage[ $block['blockName'] ]++;

			// Build block data
			$block_data = array(
				'name'  => $block['blockName'],
				'attrs' => $block['attrs'] ?? array(),
				'html'  => $this->sanitize_block_html( $block['innerHTML'] ?? '' ),
			);

			// Recursively parse inner blocks
			if ( ! empty( $block['innerBlocks'] ) ) {
				$block_data['innerBlocks'] = $this->parse_and_track_blocks( $block['innerBlocks'] );
			}

			$parsed[] = $block_data;
		}

		return $parsed;
	}

	/**
	 * Sanitize block HTML content.
	 *
	 * @param string $html Raw HTML content.
	 * @return string Sanitized HTML.
	 */
	private function sanitize_block_html( $html ) {
		// Remove excessive whitespace but preserve structure
		$html = trim( $html );
		
		// Allow all HTML tags for content preservation
		// In a real migration, we want to preserve the exact HTML
		return $html;
	}

	/**
	 * Get taxonomies and terms for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return array Taxonomies with term IDs.
	 */
	private function get_post_taxonomies( $post ) {
		$taxonomies = get_object_taxonomies( $post->post_type );
		$taxonomy_data = array();

		foreach ( $taxonomies as $taxonomy ) {
			$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'ids' ) );
			
			if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
				$taxonomy_data[ $taxonomy ] = $terms;
			}
		}

		return $taxonomy_data;
	}

	/**
	 * Get featured media information.
	 *
	 * @param int $post_id Post ID.
	 * @return array|null Featured media data or null.
	 */
	private function get_featured_media( $post_id ) {
		$thumbnail_id = get_post_thumbnail_id( $post_id );
		
		if ( ! $thumbnail_id ) {
			return null;
		}

		$attachment = get_post( $thumbnail_id );
		$image_url = wp_get_attachment_url( $thumbnail_id );
		$alt_text = get_post_meta( $thumbnail_id, '_wp_attachment_image_alt', true );

		return array(
			'id'  => $thumbnail_id,
			'url' => $image_url,
			'alt' => $alt_text,
		);
	}

	/**
	 * Get post metadata with filtering.
	 *
	 * @param int    $post_id Post ID.
	 * @param string $post_type Post type.
	 * @return array Filtered postmeta.
	 */
	private function get_post_metadata( $post_id, $post_type ) {
		// Get all postmeta for this post
		$all_meta = get_post_meta( $post_id );
		
		if ( empty( $all_meta ) ) {
			return array();
		}

		$filtered_meta = Moltex_Exporter_Security_Filters::filter_export_meta( $all_meta );

		// For attachment post type, include additional metadata
		if ( $post_type === 'attachment' ) {
			$filtered_meta = $this->add_attachment_metadata( $post_id, $filtered_meta );
		}

		return $filtered_meta;
	}

	/**
	 * Move `__<id>` postmeta keys out of the item (C10).
	 *
	 * These keys hold another post's meta (a revision or duplicate) nested into
	 * this one. Values are dropped; only the key names and the origin id remain,
	 * and legacy `url|id||::` gallery strings are never exported.
	 *
	 * @param array $postmeta Filtered postmeta, modified in place.
	 * @return array Diagnostics.
	 */
	private function extract_nested_postmeta( array &$postmeta ) {
		$diagnostics = array();
		foreach ( array_keys( $postmeta ) as $key ) {
			if ( ! preg_match( '/^__(\d+)$/', (string) $key, $match ) ) {
				continue;
			}
			$value = $postmeta[ $key ];
			$diagnostics[] = array(
				'key'            => (string) $key,
				'origin_post_id' => (int) $match[1],
				'meta_keys'      => is_array( $value ) ? array_values( array_map( 'strval', array_keys( $value ) ) ) : array(),
				'explanation'    => 'Postmeta of another post nested under this item; values withheld. Use geodirectory.media for images.',
			);
			unset( $postmeta[ $key ] );
		}
		if ( isset( $postmeta['post_images'] ) && is_string( $postmeta['post_images'] ) && false !== strpos( $postmeta['post_images'], '|' ) ) {
			unset( $postmeta['post_images'] );
			$diagnostics[] = array( 'key' => 'post_images', 'origin_post_id' => null, 'meta_keys' => array(), 'explanation' => 'Legacy pipe-separated gallery string dropped; use geodirectory.media.' );
		}
		return $diagnostics;
	}

	/**
	 * Parse a GeoDirectory business_hours value (C9).
	 *
	 * Source format: ["Mo 09:00-17:00,19:00-23:00","Tu 12:00-00:00"],["UTC":"-5","Timezone":"America/Guayaquil"]
	 *
	 * @param string $value Raw value.
	 * @return array|null
	 */
	public static function parse_business_hours( $value ) {
		if ( ! is_string( $value ) || ! preg_match( '/\b(Mo|Tu|We|Th|Fr|Sa|Su)\s+\d{1,2}:\d{2}/', $value ) ) {
			return null;
		}
		$days = array();
		if ( preg_match_all( '/\b(Mo|Tu|We|Th|Fr|Sa|Su)\s+((?:\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*,?\s*)+)/', $value, $matches, PREG_SET_ORDER ) ) {
			foreach ( $matches as $match ) {
				preg_match_all( '/(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})/', $match[2], $ranges, PREG_SET_ORDER );
				foreach ( $ranges as $range ) {
					$days[ strtolower( $match[1] ) ][] = array( 'open' => $range[1], 'close' => $range[2] );
				}
			}
		}
		$utc_offset = preg_match( '/"UTC"\s*:\s*"([^"]*)"/', $value, $m ) ? $m[1] : null;
		$timezone = preg_match( '/"Timezone(?:_string)?"\s*:\s*"([^"]*)"/', $value, $m ) ? stripslashes( $m[1] ) : null;
		return array(
			'days'       => $days,
			'utc_offset' => '' === $utc_offset ? null : $utc_offset,
			'timezone'   => '' === $timezone ? null : $timezone,
		);
	}

	/**
	 * Add attachment-specific metadata.
	 *
	 * @param int   $attachment_id Attachment ID.
	 * @param array $meta Existing meta array.
	 * @return array Meta with attachment data added.
	 */
	private function add_attachment_metadata( $attachment_id, $meta ) {
		// Get attachment metadata
		$attachment_meta = wp_get_attachment_metadata( $attachment_id );
		
		if ( ! empty( $attachment_meta ) ) {
			$meta['_wp_attachment_metadata'] = $attachment_meta;
		}

		// Get alt text (already in meta, but ensure it's included)
		$alt_text = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );
		if ( ! empty( $alt_text ) ) {
			$meta['_wp_attachment_image_alt'] = $alt_text;
		}

		// Get attachment URL
		$attachment_url = wp_get_attachment_url( $attachment_id );
		if ( $attachment_url ) {
			$meta['_attachment_url'] = $attachment_url;
		}

		// Get MIME type
		$mime_type = get_post_mime_type( $attachment_id );
		if ( $mime_type ) {
			$meta['_mime_type'] = $mime_type;
		}

		return $meta;
	}

	/**
	 * Extract internal links from content.
	 *
	 * @param string $content Post content.
	 * @return array Internal link paths.
	 */
	private function extract_internal_links( $content ) {
		$internal_links = array();
		$site_url = get_site_url();
		
		// Match all href attributes
		preg_match_all( '/<a[^>]+href=["\']([^"\']+)["\'][^>]*>/i', $content, $matches );
		
		if ( ! empty( $matches[1] ) ) {
			foreach ( $matches[1] as $url ) {
				// Check if it's an internal link
				if ( strpos( $url, $site_url ) === 0 ) {
					// Convert to relative path
					$path = str_replace( $site_url, '', $url );
					$internal_links[] = $path;
				} elseif ( strpos( $url, '/' ) === 0 && strpos( $url, '//' ) !== 0 ) {
					// Already a relative path
					$internal_links[] = $url;
				}
			}
		}

		return array_unique( $internal_links );
	}

	/**
	 * Get legacy permalink for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return string Legacy permalink.
	 */
	private function get_legacy_permalink( $post ) {
		$permalink = get_permalink( $post->ID );
		$site_url = get_site_url();
		
		// Convert to relative path
		return str_replace( $site_url, '', $permalink );
	}

	/**
	 * Get block usage statistics.
	 *
	 * @return array Top blocks by usage count.
	 */
	private function get_block_usage_stats() {
		// Sort by usage count descending
		arsort( $this->block_usage );

		// Convert to array format
		$stats = array();
		foreach ( $this->block_usage as $block_name => $count ) {
			$stats[] = array(
				'name'  => $block_name,
				'count' => $count,
			);
		}

		return $stats;
	}

	/**
	 * Check if a post type is a GeoDirectory custom post type.
	 *
	 * @param string $post_type Post type name.
	 * @return bool True if GeoDirectory CPT.
	 */
	private function is_geodirectory_cpt( $post_type ) {
		if ( function_exists( 'geodir_get_posttypes' ) ) {
			$post_types = geodir_get_posttypes();
			if ( is_array( $post_types ) && in_array( $post_type, $post_types, true ) ) {
				return true;
			}
		}

		// GeoDirectory v2 stores listing data in one detail table per CPT. This
		// remains authoritative when optional taxonomy registration is absent.
		if ( $this->get_geodir_detail_table( $post_type ) ) {
			return true;
		}

		if ( taxonomy_exists( 'geodir_cpt' ) ) {
			$taxonomies = get_object_taxonomies( $post_type );
			return in_array( 'geodir_cpt', $taxonomies, true );
		}

		return false;
	}

	/**
	 * Get GeoDirectory-specific metadata for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return array GeoDirectory metadata.
	 */
	private function get_geodirectory_metadata( $post ) {
		global $wpdb;

		$geodir_data = array();

		// Get the detail table name for this post type
		$detail_table = $this->get_geodir_detail_table( $post->post_type );

		// Read metadata from GeoDirectory custom table if it exists
		if ( $detail_table ) {
			$detail_data = $wpdb->get_row(
				$wpdb->prepare(
					"SELECT * FROM {$detail_table} WHERE post_id = %d",
					$post->ID
				),
				ARRAY_A
			);

			if ( $detail_data ) {
				$address = array();
				foreach ( array( 'street', 'street2', 'city', 'region', 'country', 'zip', 'postcode', 'neighbourhood', 'location_id' ) as $key ) {
					if ( isset( $detail_data[ $key ] ) && '' !== $detail_data[ $key ] ) {
						$address[ $key ] = (string) $detail_data[ $key ];
					}
				}
				if ( ! empty( $address ) ) {
					$geodir_data['address'] = $address;
				}

				$geo = array();
				foreach ( array( 'latitude', 'longitude' ) as $key ) {
					if ( isset( $detail_data[ $key ] ) && is_numeric( $detail_data[ $key ] ) ) {
						$geo[ $key ] = (float) $detail_data[ $key ];
					}
				}
				if ( ! empty( $geo ) ) {
					$geodir_data['geo'] = $geo;
				}

				$custom_fields = array();
				foreach ( $this->get_geodirectory_field_definitions( $post->post_type ) as $definition ) {
					$key = $definition['key'];
					if ( array_key_exists( $key, $detail_data ) ) {
						$custom_fields[ $key ] = $this->normalize_geodirectory_value( $detail_data[ $key ], $definition );
					}
				}
				// Operator-allowlisted admin columns (C1), e.g. featured, package_id, expire_date.
				foreach ( Moltex_Exporter_Export_Policy::get( 'geodirectory_include_fields' ) as $key ) {
					if ( ! array_key_exists( $key, $custom_fields ) && array_key_exists( $key, $detail_data ) && ! $this->is_never_exported_geodirectory_field( $key ) ) {
						$custom_fields[ $key ] = $this->normalize_geodirectory_value( $detail_data[ $key ], $this->find_geodirectory_definition( $post->post_type, $key ) );
					}
				}
				if ( ! empty( $custom_fields ) ) {
					$geodir_data['custom_fields'] = $custom_fields;
				}
				$hours_raw = isset( $custom_fields['business_hours'] ) ? $custom_fields['business_hours'] : null;
				if ( is_array( $hours_raw ) ) {
					$hours_raw = wp_json_encode( $hours_raw );
				}
				$hours = self::parse_business_hours( $hours_raw );
				if ( null !== $hours ) {
					$geodir_data['business_hours'] = $hours;
				}

				// Contact presence without the address itself (C1).
				$has_email = false;
				foreach ( $detail_data as $column => $value ) {
					if ( false !== stripos( (string) $column, 'email' ) && is_scalar( $value ) && '' !== trim( (string) $value ) ) {
						$has_email = true;
						break;
					}
				}
				$geodir_data['contact_flags'] = array( 'has_email' => $has_email );

				// Values stored in columns with no field definition (C3), key names only.
				$undeclared = $this->get_undeclared_geodirectory_columns( $post->post_type, $detail_data );
				if ( ! empty( $undeclared ) ) {
					$geodir_data['diagnostics']['undeclared_value_columns'] = $undeclared;
					$this->log_warning( 'content', sprintf( 'GeoDirectory %s post %d has values in undeclared columns: %s', $post->post_type, $post->ID, implode( ', ', $undeclared ) ) );
				}
			}
		}

		// Older releases can keep public contact fields in postmeta. Email is
		// deliberately omitted from this privacy-filtered migration bundle.
		$geodir_meta_keys = array(
			'geodir_contact',
			'geodir_website',
			'geodir_phone',
			'geodir_twitter',
			'geodir_facebook',
			'geodir_video',
			'geodir_timing',
			'geodir_featured',
			'geodir_special_offers',
		);

		$postmeta = array();
		foreach ( $geodir_meta_keys as $meta_key ) {
			$value = get_post_meta( $post->ID, $meta_key, true );
			if ( ! empty( $value ) ) {
				$postmeta[ $meta_key ] = $value;
			}
		}

		if ( ! empty( $postmeta ) ) {
			$geodir_data['legacy_public_postmeta'] = $postmeta;
		}

		$media = $this->get_geodirectory_media( $post->ID );
		if ( ! empty( $media ) ) {
			$geodir_data['media'] = $media;
		}

		$reviews = $this->get_geodirectory_reviews( $post->ID );
		if ( ! empty( $reviews ) ) {
			$geodir_data['reviews'] = $reviews;
			$ratings = array_values( array_filter( array_column( $reviews, 'rating' ), 'is_numeric' ) );
			$geodir_data['review_summary'] = array(
				'count'          => count( $reviews ),
				'average_rating' => ! empty( $ratings ) ? array_sum( $ratings ) / count( $ratings ) : null,
			);
		}

		// Get categories (from GeoDirectory category taxonomies)
		$category_taxonomies = $this->get_geodir_category_taxonomies( $post->post_type );
		if ( ! empty( $category_taxonomies ) ) {
			$categories = array();
			foreach ( $category_taxonomies as $taxonomy ) {
				$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'all' ) );
				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					foreach ( $terms as $term ) {
						$categories[] = array(
							'taxonomy' => $taxonomy,
							'term_id'  => $term->term_id,
							'name'     => $term->name,
							'slug'     => $term->slug,
						);
					}
				}
			}
			if ( ! empty( $categories ) ) {
				$geodir_data['categories'] = $categories;
			}
		}

		// Get tags/amenities (from GeoDirectory tags taxonomies)
		$tags_taxonomies = $this->get_geodir_tags_taxonomies( $post->post_type );
		if ( ! empty( $tags_taxonomies ) ) {
			$tags = array();
			foreach ( $tags_taxonomies as $taxonomy ) {
				$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'all' ) );
				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					foreach ( $terms as $term ) {
						$tags[] = array(
							'taxonomy' => $taxonomy,
							'term_id'  => $term->term_id,
							'name'     => $term->name,
							'slug'     => $term->slug,
						);
					}
				}
			}
			if ( ! empty( $tags ) ) {
				$geodir_data['tags'] = $tags;
			}
		}

		return $geodir_data;
	}

	/**
	 * Get the GeoDirectory detail table name for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return string|null Table name or null if not found.
	 */
	private function get_geodir_detail_table( $post_type ) {
		global $wpdb;
		if ( array_key_exists( $post_type, $this->geodir_detail_tables ) ) {
			return $this->geodir_detail_tables[ $post_type ];
		}

		if ( ! preg_match( '/^[a-z0-9_]+$/', $post_type ) ) {
			$this->geodir_detail_tables[ $post_type ] = null;
			return null;
		}

		$table_name = $wpdb->prefix . 'geodir_' . $post_type . '_detail';
		$this->geodir_detail_tables[ $post_type ] = $this->geodirectory_table_exists( $table_name ) ? $table_name : null;
		return $this->geodir_detail_tables[ $post_type ];
	}

	/**
	 * Build the bounded GeoDirectory source contract used downstream.
	 *
	 * @param array $candidate_post_types Public CPT names.
	 * @return array
	 */
	private function get_geodirectory_configuration( array $candidate_post_types ) {
		$config = array(
			'schema_version' => 1,
			'post_types'     => array(),
			'privacy'        => array( 'excluded_field_keys' => array() ),
		);

		foreach ( array_values( array_unique( $candidate_post_types ) ) as $post_type ) {
			if ( ! $this->is_geodirectory_cpt( $post_type ) ) {
				continue;
			}

			$public_fields = array();
			$all_fields = array();
			$dispositions = array();
			foreach ( $this->get_geodirectory_field_definitions( $post_type, true ) as $definition ) {
				$all_fields[] = array(
					'key'                => $definition['key'],
					'label'              => $definition['label'],
					'disposition'        => $definition['disposition'],
					'is_active'          => $definition['is_active'],
					'publicly_displayed' => $definition['publicly_displayed'],
					'definition'         => $definition['source_definition'],
				);
				$bucket = false !== strpos( $definition['disposition'], ':' ) ? substr( $definition['disposition'], 0, strpos( $definition['disposition'], ':' ) ) : $definition['disposition'];
				$dispositions[ $bucket ] = isset( $dispositions[ $bucket ] ) ? $dispositions[ $bucket ] + 1 : 1;
				if ( empty( $definition['public'] ) ) {
					if ( 'operator_included' !== $definition['disposition'] ) {
						$config['privacy']['excluded_field_keys'][] = $definition['key'];
					}
					continue;
				}
				$field = array_intersect_key( $definition, array_flip( array( 'key', 'label', 'data_type', 'field_type', 'show_in', 'sort_order' ) ) );
				$public_fields[] = $field;
			}
			ksort( $dispositions, SORT_STRING );
			$unkeyed = isset( $this->geodir_unkeyed_field_rows[ $post_type ] ) ? $this->geodir_unkeyed_field_rows[ $post_type ] : array();
			if ( ! empty( $unkeyed ) ) {
				$dispositions['no_htmlvar_name'] = count( $unkeyed );
				ksort( $dispositions, SORT_STRING );
			}

			$config['post_types'][ $post_type ] = array(
				'detail_storage'=> 'geodirectory_cpt_detail',
				'fields'        => $public_fields,
				'all_fields'    => $all_fields,
				'unkeyed_rows'  => $unkeyed,
				'field_summary' => array( 'source_rows' => count( $all_fields ) + count( $unkeyed ), 'by_disposition' => $dispositions ),
				'search_fields' => $this->get_geodirectory_behavior_rows( 'custom_advance_search_fields', $post_type ),
				'sort_fields'   => $this->get_geodirectory_behavior_rows( 'custom_sort_fields', $post_type ),
				'tabs'          => $this->get_geodirectory_behavior_rows( 'tabs_layout', $post_type ),
			);
		}

		$config['rating_criteria']       = $this->dump_geodirectory_table( 'rating_category', 'display_order' );
		$config['field_reconciliation']  = $this->get_geodirectory_field_reconciliation( array_keys( $config['post_types'] ) );
		$config['rating_styles']         = $this->dump_geodirectory_table( 'rating_style', 'id' );
		$config['review_reconciliation'] = $this->get_geodirectory_review_reconciliation();
		$config['attachment_reconciliation'] = $this->get_geodirectory_attachment_reconciliation();
		$config['locations']             = array(
			'locations'      => $this->dump_geodirectory_table( 'post_locations', 'location_id' ),
			'neighbourhoods' => $this->dump_geodirectory_table( 'post_neighbourhood', 'hood_id' ),
			'location_seo'   => $this->dump_geodirectory_table( 'location_seo', 'seo_id' ),
		);
		$config['sort_fields_all']       = $this->dump_geodirectory_table( 'custom_sort_fields', 'sort_order' );
		$config['advanced_search']       = $this->get_geodirectory_search_settings();

		$config['privacy']['excluded_field_keys'] = array_values( array_unique( $config['privacy']['excluded_field_keys'] ) );
		sort( $config['privacy']['excluded_field_keys'], SORT_STRING );
		ksort( $config['post_types'], SORT_STRING );
		return $config;
	}

	/**
	 * Return field definitions and their public/private disposition.
	 *
	 * @param string $post_type GeoDirectory CPT.
	 * @param bool   $include_private Include definitions excluded from values.
	 * @return array
	 */
	private function get_geodirectory_field_definitions( $post_type, $include_private = false ) {
		global $wpdb;
		if ( ! isset( $this->geodir_field_definitions[ $post_type ] ) ) {
			$table = $wpdb->prefix . 'geodir_custom_fields';
			$definitions = array();
			if ( $this->geodirectory_table_exists( $table ) ) {
				$rows = $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A );
				$this->geodir_field_rows = is_array( $rows ) ? $rows : array();
				$this->geodir_unkeyed_field_rows[ $post_type ] = array();
				foreach ( is_array( $rows ) ? $rows : array() as $row ) {
					if ( is_array( $row ) && $post_type === ( isset( $row['post_type'] ) ? $row['post_type'] : '' ) && empty( $row['htmlvar_name'] ) ) {
						// Fieldsets/separators carry no column; keep them for reconciliation (C2).
						$this->geodir_unkeyed_field_rows[ $post_type ][] = array(
							'id'          => isset( $row['id'] ) ? (int) $row['id'] : 0,
							'label'       => isset( $row['frontend_title'] ) ? (string) $row['frontend_title'] : '',
							'field_type'  => isset( $row['field_type'] ) ? (string) $row['field_type'] : '',
							'disposition' => 'no_htmlvar_name',
							'is_active'   => ! empty( $row['is_active'] ),
							'definition'  => $this->describe_geodirectory_definition_row( $row ),
						);
						continue;
					}
					if ( ! is_array( $row ) || $post_type !== ( isset( $row['post_type'] ) ? $row['post_type'] : '' ) || empty( $row['htmlvar_name'] ) ) {
						continue;
					}
					$key = (string) $row['htmlvar_name'];
					$disposition = $this->geodirectory_field_disposition( $key, $row );
					$definitions[] = array(
						'key'        => $key,
						'label'      => isset( $row['frontend_title'] ) ? (string) $row['frontend_title'] : $key,
						'data_type'  => isset( $row['data_type'] ) ? strtolower( (string) $row['data_type'] ) : 'string',
						'field_type' => isset( $row['field_type'] ) ? (string) $row['field_type'] : 'text',
						'show_in'    => isset( $row['show_in'] ) ? $this->decode_geodirectory_structure( $row['show_in'] ) : array(),
						'sort_order' => isset( $row['sort_order'] ) ? (int) $row['sort_order'] : 0,
						'public'     => 'exported' === $disposition,
						'is_active'  => ! empty( $row['is_active'] ),
						'disposition'=> $disposition,
						'publicly_displayed' => ! empty( $row['is_active'] ) && empty( $row['for_admin_use'] ) && ! empty( $row['show_in'] ),
						'source_definition' => $this->describe_geodirectory_definition_row( $row ),
					);
				}
			}
			usort(
				$definitions,
				function ( $left, $right ) {
					return $left['sort_order'] <=> $right['sort_order'];
				}
			);
			$this->geodir_field_definitions[ $post_type ] = $definitions;
		}

		if ( $include_private ) {
			return $this->geodir_field_definitions[ $post_type ];
		}
		return array_values(
			array_filter(
				$this->geodir_field_definitions[ $post_type ],
				function ( $definition ) {
					return ! empty( $definition['public'] ) || 'operator_included' === $definition['disposition'];
				}
			)
		);
	}

	/**
	 * Why a field definition's values are or are not exported (C2).
	 *
	 * @param string $key Field key.
	 * @param array  $row Definition row.
	 * @return string exported|inactive|admin_only|sensitive:<needle>|operator_included
	 */
	private function geodirectory_field_disposition( $key, array $row ) {
		if ( empty( $row['is_active'] ) ) {
			return 'inactive';
		}
		$included = in_array( strtolower( $key ), Moltex_Exporter_Export_Policy::get( 'geodirectory_include_fields' ), true ) && ! $this->is_never_exported_geodirectory_field( $key );
		$needle = $this->sensitive_geodirectory_needle( $key, $row );
		if ( null !== $needle ) {
			return $included ? 'operator_included' : 'sensitive:' . $needle;
		}
		if ( ! empty( $row['for_admin_use'] ) ) {
			return $included ? 'operator_included' : 'admin_only';
		}
		return 'exported';
	}

	/** Definition attributes, decoded, without values. */
	private function describe_geodirectory_definition_row( array $row ) {
		$out = array();
		foreach ( $row as $column => $value ) {
			if ( ! is_string( $column ) || ! preg_match( '/^[A-Za-z0-9_]+$/', $column ) ) {
				continue;
			}
			$out[ $column ] = in_array( $column, array( 'option_values', 'extra_fields', 'show_in', 'validation_pattern', 'packages' ), true )
				? $this->decode_geodirectory_structure( $value )
				: ( is_numeric( $value ) && (string) (int) $value === (string) $value ? (int) $value : $value );
		}
		ksort( $out, SORT_STRING );
		return $out;
	}

	/**
	 * Account for every geodir_custom_fields row (C2): per post type, and the
	 * rows of post types that were not exported, with their IDs.
	 *
	 * @param string[] $exported_types GeoDirectory CPTs present in the config.
	 * @return array
	 */
	private function get_geodirectory_field_reconciliation( array $exported_types ) {
		$rows = is_array( $this->geodir_field_rows ) ? $this->geodir_field_rows : array();
		$by_post_type = array();
		$other = array();
		foreach ( $rows as $row ) {
			if ( ! is_array( $row ) ) {
				continue;
			}
			$type = isset( $row['post_type'] ) ? (string) $row['post_type'] : '';
			$by_post_type[ $type ] = isset( $by_post_type[ $type ] ) ? $by_post_type[ $type ] + 1 : 1;
			if ( ! in_array( $type, $exported_types, true ) ) {
				$other[] = array(
					'id'           => isset( $row['id'] ) ? (int) $row['id'] : 0,
					'post_type'    => $type,
					'htmlvar_name' => isset( $row['htmlvar_name'] ) ? (string) $row['htmlvar_name'] : '',
					'reason'       => '' === $type ? 'no_post_type' : 'post_type_not_exported',
				);
			}
		}
		ksort( $by_post_type, SORT_STRING );
		return array(
			'source_rows'             => count( $rows ),
			'by_post_type'            => $by_post_type,
			'rows_outside_export'     => $other,
		);
	}

	/** Fields whose values never leave the site even when allowlisted. */
	private function is_never_exported_geodirectory_field( $key ) {
		return (bool) preg_match( '/email|password|secret|token|api_key|submit_ip/i', (string) $key );
	}

	private function find_geodirectory_definition( $post_type, $key ) {
		foreach ( $this->get_geodirectory_field_definitions( $post_type, true ) as $definition ) {
			if ( $definition['key'] === $key ) {
				return $definition;
			}
		}
		return array();
	}

	/**
	 * Non-empty detail columns that no definition declares (C3).
	 *
	 * @param string $post_type   CPT.
	 * @param array  $detail_data Detail row.
	 * @return string[]
	 */
	private function get_undeclared_geodirectory_columns( $post_type, array $detail_data ) {
		$core = array( 'post_id', 'post_title', 'post_status', 'post_category', 'default_category', 'post_tags', 'featured_image', 'submit_ip', 'overall_rating', 'rating_count', 'street', 'street2', 'city', 'region', 'country', 'zip', 'postcode', 'latitude', 'longitude', 'mapview', 'mapzoom', 'post_dummy', 'marker_json', 'location_id', 'neighbourhood', 'featured', 'package_id', 'expire_date', 'post_date', 'post_modified', 'ratings', 'post_images', 'address' );
		$declared = array();
		foreach ( $this->get_geodirectory_field_definitions( $post_type, true ) as $definition ) {
			$declared[ $definition['key'] ] = true;
		}
		$undeclared = array();
		foreach ( $detail_data as $column => $value ) {
			if ( isset( $declared[ $column ] ) || in_array( $column, $core, true ) || null === $value || '' === trim( (string) ( is_scalar( $value ) ? $value : 'x' ) ) ) {
				continue;
			}
			$undeclared[] = (string) $column;
		}
		sort( $undeclared, SORT_STRING );
		return $undeclared;
	}

	/** Determine whether a GeoDirectory column must never enter the bundle. */
	private function is_sensitive_geodirectory_field( $key, array $definition = array() ) {
		return null !== $this->sensitive_geodirectory_needle( $key, $definition );
	}

	/** The sensitive pattern a field matches, or null. */
	private function sensitive_geodirectory_needle( $key, array $definition = array() ) {
		$value = strtolower( $key . ' ' . ( isset( $definition['field_type'] ) ? $definition['field_type'] : '' ) );
		foreach ( array( 'email', 'password', 'secret', 'token', 'api_key', 'submit_ip', 'user_id', 'owner_id', 'payment', 'transaction', 'invoice', 'package_id', 'admin_note' ) as $needle ) {
			if ( false !== strpos( $value, $needle ) ) {
				return $needle;
			}
		}
		return null;
	}

	/** Normalize a public field without guessing beyond its declared type. */
	private function normalize_geodirectory_value( $value, array $definition = array() ) {
		$value = maybe_unserialize( $value );
		if ( ! is_string( $value ) ) {
			return $value;
		}
		$type = isset( $definition['data_type'] ) ? strtolower( $definition['data_type'] ) : '';
		$field_type = isset( $definition['field_type'] ) ? strtolower( $definition['field_type'] ) : '';
		if ( in_array( $field_type, array( 'checkbox', 'toggle' ), true ) ) {
			return in_array( strtolower( $value ), array( '1', 'true', 'yes', 'on' ), true );
		}
		if ( preg_match( '/(^|[^a-z])(tinyint|smallint|mediumint|int|bigint)([^a-z]|$)/', $type ) ) {
			return (int) $value;
		}
		if ( preg_match( '/(float|double|decimal|numeric)/', $type ) ) {
			return (float) $value;
		}
		return $this->decode_geodirectory_structure( $value );
	}

	/** Decode JSON/serialized structures while preserving plain strings. */
	private function decode_geodirectory_structure( $value ) {
		$value = maybe_unserialize( $value );
		if ( ! is_string( $value ) ) {
			return $value;
		}
		$decoded = json_decode( $value, true );
		return JSON_ERROR_NONE === json_last_error() ? $decoded : $value;
	}

	/** Export approved public gallery relationships without uploader identity. */
	private function get_geodirectory_media( $post_id ) {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_attachments';
		if ( ! $this->geodirectory_table_exists( $table ) ) {
			return array();
		}
		$rows = $wpdb->get_results(
			$wpdb->prepare( "SELECT ID, title, caption, file, mime_type, menu_order, featured, metadata FROM {$table} WHERE post_id = %d AND is_approved = 1 ORDER BY menu_order, ID", $post_id ),
			ARRAY_A
		);
		$media = array();
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			$url = $this->resolve_geodirectory_media_url( isset( $row['file'] ) ? $row['file'] : '' );
			if ( ! $url ) {
				continue;
			}
			$media[] = array(
				'url'      => $url,
				'alt'      => isset( $row['title'] ) ? (string) $row['title'] : '',
				'metadata' => array(
					'id'         => 'geodirectory:' . ( isset( $row['ID'] ) ? (int) $row['ID'] : 0 ),
					'source'     => 'geodirectory',
					'title'      => isset( $row['title'] ) ? (string) $row['title'] : '',
					'caption'    => isset( $row['caption'] ) ? (string) $row['caption'] : '',
					'mime_type'  => isset( $row['mime_type'] ) ? (string) $row['mime_type'] : '',
					'menu_order' => isset( $row['menu_order'] ) ? (int) $row['menu_order'] : 0,
					'featured'   => ! empty( $row['featured'] ),
				),
			);
		}
		return $media;
	}

	/** Resolve a GeoDirectory attachment path against WordPress uploads. */
	private function resolve_geodirectory_media_url( $file ) {
		$file = trim( (string) $file );
		if ( '' === $file ) {
			return null;
		}
		if ( preg_match( '#^https?://#i', $file ) ) {
			return $file;
		}
		$uploads = wp_upload_dir();
		if ( empty( $uploads['baseurl'] ) ) {
			return null;
		}
		if ( false !== strpos( $file, '/wp-content/uploads/' ) ) {
			$file = substr( $file, strpos( $file, '/wp-content/uploads/' ) + strlen( '/wp-content/uploads/' ) );
		}
		return trailingslashit( $uploads['baseurl'] ) . ltrim( $file, '/\\' );
	}

	/** Export approved reviews without email, IP, or WordPress user IDs. */
	private function get_geodirectory_reviews( $post_id ) {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_post_review';
		if ( ! $this->geodirectory_table_exists( $table ) ) {
			return array();
		}
		$rows = $wpdb->get_results(
			$wpdb->prepare( "SELECT c.comment_ID, c.comment_author, c.comment_date_gmt, c.comment_content, r.rating, r.ratings FROM {$wpdb->comments} c INNER JOIN {$table} r ON r.comment_id = c.comment_ID WHERE c.comment_post_ID = %d AND c.comment_approved = '1' ORDER BY c.comment_date_gmt, c.comment_ID", $post_id ),
			ARRAY_A
		);
		$images = array();
		$attachments = $wpdb->prefix . 'geodir_attachments';
		if ( ! empty( $rows ) && $this->geodirectory_table_exists( $attachments ) ) {
			foreach ( (array) $wpdb->get_results( $wpdb->prepare( "SELECT other_id, file, title, menu_order FROM {$attachments} WHERE post_id = %d AND type = 'comment_images' AND is_approved = 1 ORDER BY other_id, menu_order", $post_id ), ARRAY_A ) as $image ) {
				$images[ (int) $image['other_id'] ][] = array(
					'file'       => (string) $image['file'],
					'title'      => isset( $image['title'] ) ? (string) $image['title'] : '',
					'menu_order' => isset( $image['menu_order'] ) ? (int) $image['menu_order'] : 0,
				);
			}
		}
		$reviews = array();
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			$comment_id = isset( $row['comment_ID'] ) ? (int) $row['comment_ID'] : 0;
			$reviews[] = array(
				'source_id' => $comment_id,
				'author'    => isset( $row['comment_author'] ) ? (string) $row['comment_author'] : '',
				'date_gmt'  => isset( $row['comment_date_gmt'] ) ? (string) $row['comment_date_gmt'] : '',
				'content'   => isset( $row['comment_content'] ) ? (string) $row['comment_content'] : '',
				'rating'    => isset( $row['rating'] ) && is_numeric( $row['rating'] ) ? (float) $row['rating'] : null,
				'ratings'   => isset( $row['ratings'] ) ? $this->decode_geodirectory_structure( $row['ratings'] ) : array(),
				// Only approved reviews are exported; the rest are counted in review_reconciliation (C5).
				'approval_status' => 'approved',
				'images'    => isset( $images[ $comment_id ] ) ? $images[ $comment_id ] : array(),
			);
		}
		return $reviews;
	}

	/**
	 * GeoDirectory search blocks and shortcodes placed in content, with attributes (C7).
	 *
	 * @param string $content Raw post content.
	 * @return array[] {kind block|shortcode, name, attrs}
	 */
	public static function find_search_placements( $content ) {
		$found = array();
		if ( preg_match_all( '#<!--\s+wp:(geodirectory/geodir-widget-(?:search|advanced-search|map|listings)|geodirectory/[a-z0-9-]*search[a-z0-9-]*)\s*(\{.*?\})?\s*/?-->#s', $content, $blocks, PREG_SET_ORDER ) ) {
			foreach ( $blocks as $match ) {
				if ( false === strpos( $match[1], 'search' ) ) {
					continue;
				}
				$attrs = isset( $match[2] ) ? json_decode( $match[2], true ) : array();
				$found[] = array( 'kind' => 'block', 'name' => $match[1], 'attrs' => is_array( $attrs ) ? $attrs : array() );
			}
		}
		if ( preg_match_all( '/\[(gd_search|gd_advanced_search|gd_search_form)\b([^\]]*)\]/', $content, $codes, PREG_SET_ORDER ) ) {
			foreach ( $codes as $match ) {
				$attrs = array();
				if ( preg_match_all( '/([a-z_][a-z0-9_-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))/i', $match[2], $pairs, PREG_SET_ORDER ) ) {
					foreach ( $pairs as $pair ) {
						$attrs[ $pair[1] ] = isset( $pair[4] ) && '' !== $pair[4] ? $pair[4] : ( isset( $pair[3] ) && '' !== $pair[3] ? $pair[3] : $pair[2] );
					}
				}
				$found[] = array( 'kind' => 'shortcode', 'name' => $match[1], 'attrs' => $attrs );
			}
		}
		return $found;
	}

	/** Export public search, sort, and tab configuration for a CPT. */
	private function get_geodirectory_behavior_rows( $suffix, $post_type ) {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_' . $suffix;
		if ( ! $this->geodirectory_table_exists( $table ) ) {
			return array();
		}
		$rows = $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A );
		$output = array();
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			if ( ! is_array( $row ) || $post_type !== ( isset( $row['post_type'] ) ? $row['post_type'] : '' ) || ( isset( $row['is_active'] ) && empty( $row['is_active'] ) ) ) {
				continue;
			}
			$key = isset( $row['htmlvar_name'] ) ? $row['htmlvar_name'] : ( isset( $row['tab_key'] ) ? $row['tab_key'] : '' );
			if ( $key && $this->is_sensitive_geodirectory_field( $key, $row ) ) {
				continue;
			}
			if ( 'tabs_layout' === $suffix ) {
				$output[] = array(
					'key'        => (string) $key,
					'name'       => isset( $row['tab_name'] ) ? (string) $row['tab_name'] : '',
					'type'       => isset( $row['tab_type'] ) ? (string) $row['tab_type'] : '',
					'layout'     => isset( $row['tab_layout'] ) ? (string) $row['tab_layout'] : '',
					'content'    => isset( $row['tab_content'] ) ? (string) $row['tab_content'] : '',
					'sort_order' => isset( $row['sort_order'] ) ? (int) $row['sort_order'] : 0,
				);
			} else {
				$output[] = array(
					'key'        => (string) $key,
					'label'      => isset( $row['frontend_title'] ) ? (string) $row['frontend_title'] : (string) $key,
					'data_type'  => isset( $row['data_type'] ) ? strtolower( (string) $row['data_type'] ) : 'string',
					'field_type' => isset( $row['field_type'] ) ? (string) $row['field_type'] : '',
					'sort'       => isset( $row['sort'] ) ? (string) $row['sort'] : '',
					'sort_order' => isset( $row['sort_order'] ) ? (int) $row['sort_order'] : 0,
				);
			}
		}
		return $output;
	}

	/**
	 * Every row of a GeoDirectory configuration table, decoded (C5, C6, C7).
	 *
	 * Sensitive-looking columns (email, IP, user/owner IDs) are dropped.
	 *
	 * @param string $suffix   Table suffix after `geodir_`.
	 * @param string $order_by Column to sort by in PHP.
	 * @return array[]
	 */
	private function dump_geodirectory_table( $suffix, $order_by ) {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_' . $suffix;
		if ( ! preg_match( '/^[a-z_]+$/', $suffix ) || ! $this->geodirectory_table_exists( $table ) ) {
			return array();
		}
		$rows = $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A );
		$output = array();
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			if ( ! is_array( $row ) ) {
				continue;
			}
			foreach ( array_keys( $row ) as $column ) {
				if ( preg_match( '/email|_ip$|^ip$|user_id|owner_id|password|token/i', (string) $column ) ) {
					unset( $row[ $column ] );
				}
			}
			$output[] = $this->describe_geodirectory_definition_row( $row );
		}
		usort(
			$output,
			function ( $left, $right ) use ( $order_by ) {
				$a = isset( $left[ $order_by ] ) ? $left[ $order_by ] : 0;
				$b = isset( $right[ $order_by ] ) ? $right[ $order_by ] : 0;
				return $a <=> $b;
			}
		);
		return $output;
	}

	/**
	 * Why each review row was or was not exported (C5).
	 *
	 * @return array
	 */
	/**
	 * Account for every geodir_attachments row by type and reason (M1).
	 *
	 * @return array {source_rows, by_type:{type:{reason:count}}}
	 */
	private function get_geodirectory_attachment_reconciliation() {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_attachments';
		if ( ! $this->geodirectory_table_exists( $table ) ) {
			return array( 'source_rows' => 0, 'by_type' => array() );
		}
		$rows = $wpdb->get_results( "SELECT a.type AS type, a.is_approved AS approved, p.post_status AS post_status, COUNT(*) AS total FROM {$table} a LEFT JOIN {$wpdb->posts} p ON p.ID = a.post_id GROUP BY a.type, a.is_approved, p.post_status", ARRAY_A );
		$by_type = array();
		$total = 0;
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			$count = (int) $row['total'];
			$type = '' !== (string) $row['type'] ? (string) $row['type'] : 'unknown';
			if ( null === $row['post_status'] ) {
				$reason = 'listing_missing';
			} elseif ( 'publish' !== $row['post_status'] ) {
				$reason = 'listing_' . preg_replace( '/[^a-z0-9_-]/', '', strtolower( (string) $row['post_status'] ) );
			} elseif ( empty( $row['approved'] ) ) {
				$reason = 'unapproved';
			} else {
				$reason = 'exported';
			}
			$by_type[ $type ][ $reason ] = ( isset( $by_type[ $type ][ $reason ] ) ? $by_type[ $type ][ $reason ] : 0 ) + $count;
			$total += $count;
		}
		ksort( $by_type );
		foreach ( $by_type as &$reasons ) {
			ksort( $reasons );
		}
		unset( $reasons );
		return array( 'source_rows' => $total, 'by_type' => $by_type );
	}

	private function get_geodirectory_review_reconciliation() {
		global $wpdb;
		$table = $wpdb->prefix . 'geodir_post_review';
		if ( ! $this->geodirectory_table_exists( $table ) ) {
			return array();
		}
		$rows = $wpdb->get_results( "SELECT c.comment_approved AS approved, p.post_status AS post_status, COUNT(*) AS total FROM {$table} r LEFT JOIN {$wpdb->comments} c ON c.comment_ID = r.comment_id LEFT JOIN {$wpdb->posts} p ON p.ID = r.post_id GROUP BY c.comment_approved, p.post_status", ARRAY_A );
		$by_reason = array();
		$total = 0;
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			$count = isset( $row['total'] ) ? (int) $row['total'] : 0;
			$total += $count;
			$approved = isset( $row['approved'] ) ? (string) $row['approved'] : null;
			$status = isset( $row['post_status'] ) ? (string) $row['post_status'] : null;
			if ( null === $approved || '' === $approved ) {
				$reason = 'comment_missing';
			} elseif ( 'spam' === $approved ) {
				$reason = 'spam';
			} elseif ( 'trash' === $approved ) {
				$reason = 'trashed';
			} elseif ( '1' !== $approved ) {
				$reason = 'unapproved';
			} elseif ( null === $status || '' === $status ) {
				$reason = 'listing_missing';
			} elseif ( 'publish' !== $status ) {
				$reason = 'listing_' . preg_replace( '/[^a-z_]/', '', $status );
			} else {
				$reason = 'exported';
			}
			$by_reason[ $reason ] = ( isset( $by_reason[ $reason ] ) ? $by_reason[ $reason ] : 0 ) + $count;
		}
		ksort( $by_reason, SORT_STRING );
		return array( 'source_rows' => $total, 'by_reason' => $by_reason );
	}

	/** Advanced Search add-on settings stored in geodir_settings (C7). */
	private function get_geodirectory_search_settings() {
		$settings = get_option( 'geodir_settings', array() );
		$out = array();
		foreach ( is_array( $settings ) ? $settings : array() as $key => $value ) {
			if ( preg_match( '/^(advs_|search_|geodir_search|as_)/', (string) $key ) ) {
				$out[ (string) $key ] = $value;
			}
		}
		ksort( $out, SORT_STRING );
		return $out;
	}

	/** Check an exact plugin-owned table name. */
	private function geodirectory_table_exists( $table_name ) {
		global $wpdb;
		if ( ! array_key_exists( $table_name, $this->geodir_tables ) ) {
			$this->geodir_tables[ $table_name ] = (bool) $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table_name ) );
		}
		return $this->geodir_tables[ $table_name ];
	}

	/**
	 * Get GeoDirectory category taxonomies for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return array Category taxonomy names.
	 */
	private function get_geodir_category_taxonomies( $post_type ) {
		$taxonomies = get_object_taxonomies( $post_type );
		$category_taxonomies = array();

		foreach ( $taxonomies as $taxonomy ) {
			// GeoDirectory category taxonomies typically end with 'category'
			if ( strpos( $taxonomy, 'category' ) !== false && strpos( $taxonomy, 'gd_' ) === 0 ) {
				$category_taxonomies[] = $taxonomy;
			}
		}

		return $category_taxonomies;
	}

	/**
	 * Get GeoDirectory tags/amenities taxonomies for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return array Tags taxonomy names.
	 */
	private function get_geodir_tags_taxonomies( $post_type ) {
		$taxonomies = get_object_taxonomies( $post_type );
		$tags_taxonomies = array();

		foreach ( $taxonomies as $taxonomy ) {
			// GeoDirectory tags taxonomies typically contain 'tags' or specific names like 'gd_amenity'
			if ( ( strpos( $taxonomy, 'tags' ) !== false || strpos( $taxonomy, 'amenity' ) !== false ) && strpos( $taxonomy, 'gd_' ) === 0 ) {
				$tags_taxonomies[] = $taxonomy;
			}
		}

		return $tags_taxonomies;
	}

	/**
	 * Generate the selected rendered HTML evidence after all content is known.
	 *
	 * @param array $content_data Exported content groups.
	 * @return void
	 */
	private function generate_selected_html_snapshots( array $content_data ) {
		if ( empty( $this->export_dir ) ) {
			return;
		}

		$mode = $this->get_html_snapshot_mode();
		if ( 'off' === $mode ) {
			return;
		}

		$candidates = 'all' === $mode
			? $this->flatten_snapshot_candidates( $content_data )
			: $this->select_bounded_snapshot_candidates( $content_data );

		foreach ( $candidates as $candidate ) {
			if ( empty( $candidate['id'] ) ) {
				continue;
			}

			$post = get_post( (int) $candidate['id'] );
			if ( $post ) {
				$this->generate_html_snapshot( $post );
			}
		}

		foreach ( $this->build_snapshot_route_plan( $content_data ) as $route ) {
			$this->snapshot_route( $route );
		}
		$this->write_snapshot_manifest();
	}

	/** @var array Snapshot manifest entries (S1). */
	private $snapshot_manifest = array();

	/** @var array sha256 => file for duplicate detection. */
	private $snapshot_hashes = array();

	/**
	 * One route per template kind: home, archives, a term archive, search, 404 (S1).
	 *
	 * @param array $content_data Content scan data.
	 * @return array[] {name, kind, url, expect_status}
	 */
	public function build_snapshot_route_plan( array $content_data ) {
		$routes = array(
			array( 'name' => 'route-home', 'kind' => 'home', 'url' => home_url( '/' ), 'expect_status' => 200 ),
		);
		$types = isset( $content_data['post_type_inventory']['post_types'] ) ? $content_data['post_type_inventory']['post_types'] : array();
		foreach ( $types as $type => $info ) {
			if ( empty( $info['public'] ) || empty( $info['exported'] ) || ! function_exists( 'get_post_type_archive_link' ) ) {
				continue;
			}
			$link = get_post_type_archive_link( $type );
			if ( $link ) {
				$routes[] = array( 'name' => 'route-archive-' . sanitize_file_name( $type ), 'kind' => 'post_type_archive', 'url' => $link, 'expect_status' => 200 );
			}
		}
		$taxonomies = isset( $content_data['taxonomies'] ) && is_array( $content_data['taxonomies'] ) ? $content_data['taxonomies'] : $this->snapshot_taxonomy_terms( $types );
		foreach ( $taxonomies as $taxonomy => $info ) {
			$terms = isset( $info['terms'] ) && is_array( $info['terms'] ) ? $info['terms'] : array();
			$term = reset( $terms );
			if ( ! is_array( $term ) || empty( $term['term_id'] ) || ! function_exists( 'get_term_link' ) ) {
				continue;
			}
			$link = get_term_link( (int) $term['term_id'], (string) $taxonomy );
			if ( is_string( $link ) && '' !== $link ) {
				$kind = false !== strpos( (string) $taxonomy, 'location' ) ? 'location_archive' : 'term_archive';
				$routes[] = array( 'name' => 'route-term-' . sanitize_file_name( (string) $taxonomy ), 'kind' => $kind, 'url' => $link, 'expect_status' => 200 );
			}
		}
		foreach ( $this->snapshot_plugin_page_routes() as $route ) {
			$routes[] = $route;
		}
		$routes[] = array( 'name' => 'route-search', 'kind' => 'search', 'url' => home_url( '/?s=a' ), 'expect_status' => 200 );
		$routes[] = array( 'name' => 'route-404', 'kind' => 'not_found', 'url' => home_url( '/moltex-snapshot-404-probe/' ), 'expect_status' => 404 );
		return $routes;
	}

	/**
	 * One non-empty term per taxonomy of each exported public post type, for
	 * category and location archive snapshots. The taxonomy scanner runs after
	 * this scanner, so the terms are looked up here.
	 *
	 * @param array $types post_type_inventory['post_types'].
	 * @return array taxonomy => {terms: [{term_id}]}
	 */
	private function snapshot_taxonomy_terms( array $types ) {
		$taxonomies = array();
		if ( ! function_exists( 'get_object_taxonomies' ) || ! function_exists( 'get_terms' ) ) {
			return $taxonomies;
		}
		foreach ( $types as $type => $info ) {
			if ( empty( $info['public'] ) || empty( $info['exported'] ) ) {
				continue;
			}
			foreach ( (array) get_object_taxonomies( $type ) as $taxonomy ) {
				if ( isset( $taxonomies[ $taxonomy ] ) || in_array( $taxonomy, array( 'nav_menu', 'link_category', 'post_format' ), true ) ) {
					continue;
				}
				$terms = get_terms( array( 'taxonomy' => $taxonomy, 'hide_empty' => true, 'number' => 1, 'orderby' => 'count', 'order' => 'DESC' ) );
				if ( is_wp_error( $terms ) || empty( $terms ) ) {
					continue;
				}
				$term = reset( $terms );
				$term_id = is_object( $term ) ? (int) $term->term_id : ( is_array( $term ) && isset( $term['term_id'] ) ? (int) $term['term_id'] : 0 );
				if ( $term_id > 0 ) {
					$taxonomies[ $taxonomy ] = array( 'terms' => array( array( 'term_id' => $term_id ) ) );
				}
			}
		}
		return $taxonomies;
	}

	/**
	 * Profile, compare, saved-list and other template pages that GeoDirectory
	 * and UsersWP assign by page ID in their settings (S1). Any setting key
	 * naming a page ("page_*" or "*_page") with a published page ID is used.
	 *
	 * @return array[]
	 */
	private function snapshot_plugin_page_routes() {
		$routes = array();
		$seen = array();
		foreach ( array( 'geodir_settings' => 'geodirectory', 'uwp_settings' => 'userswp' ) as $option => $plugin ) {
			$settings = get_option( $option, array() );
			if ( ! is_array( $settings ) ) {
				continue;
			}
			ksort( $settings, SORT_STRING );
			foreach ( $settings as $key => $value ) {
				if ( ! preg_match( '/^page_|_page$/', (string) $key ) || ! is_scalar( $value ) || ! ctype_digit( (string) $value ) || (int) $value < 1 ) {
					continue;
				}
				$page_id = (int) $value;
				$post = get_post( $page_id );
				if ( ! $post || 'publish' !== $post->post_status || isset( $seen[ $page_id ] ) ) {
					continue;
				}
				$link = get_permalink( $page_id );
				if ( ! is_string( $link ) || '' === $link ) {
					continue;
				}
				$seen[ $page_id ] = true;
				$slug = sanitize_file_name( preg_replace( '/^page_|_page$/', '', (string) $key ) );
				$routes[] = array(
					'name'          => 'route-' . $plugin . '-' . $slug,
					'kind'          => 'plugin_page:' . $plugin . ':' . $slug,
					'url'           => $link,
					'expect_status' => 200,
					'setting'       => $option . '.' . $key,
				);
			}
		}
		return $routes;
	}

	/**
	 * Fetch and save one planned route through the canonical/duplicate guard.
	 *
	 * @param array $route Route plan entry.
	 * @return bool
	 */
	private function snapshot_route( array $route ) {
		try {
			$response = Moltex_Exporter_Public_Http_Policy::get( $route['url'], array( 'timeout' => 30, 'redirection' => 5, 'headers' => array( 'User-Agent' => 'Moltex-Exporter/1.0' ) ) );
		} catch ( InvalidArgumentException $error ) {
			$response = null;
		}
		$code = ( $response && ! is_wp_error( $response ) ) ? (int) wp_remote_retrieve_response_code( $response ) : 0;
		$html = $code ? (string) wp_remote_retrieve_body( $response ) : '';
		if ( $code !== (int) $route['expect_status'] || '' === $html ) {
			$this->snapshot_manifest[] = array( 'file' => null, 'kind' => $route['kind'], 'requested_url' => $route['url'], 'status' => 'fetch_failed', 'http_status' => $code );
			return false;
		}
		return $this->save_snapshot( $route['name'] . '.html', $route['url'], $html, $route['kind'], 'not_found' !== $route['kind'] );
	}

	/**
	 * Save a snapshot unless its canonical differs or its bytes duplicate another.
	 *
	 * @return bool True when written.
	 */
	private function save_snapshot( $filename, $requested_url, $html, $kind, $check_canonical = true, $post_id = 0 ) {
		$canonical = self::extract_canonical( $html );
		$sha = hash( 'sha256', $html );
		$entry = array( 'file' => 'snapshots/' . $filename, 'kind' => $kind, 'requested_url' => $requested_url, 'canonical' => $canonical, 'sha256' => $sha );
		if ( $post_id > 0 ) {
			$entry['post_id'] = (int) $post_id;
		}
		if ( $check_canonical && null !== $canonical && ! self::same_url( $canonical, $requested_url ) ) {
			$entry['file'] = null;
			$entry['status'] = 'canonical_mismatch';
		} elseif ( isset( $this->snapshot_hashes[ $sha ] ) ) {
			$entry['file'] = null;
			$entry['status'] = 'duplicate';
			$entry['duplicate_of'] = $this->snapshot_hashes[ $sha ];
		} else {
			$dir = trailingslashit( $this->export_dir ) . 'snapshots';
			if ( ! file_exists( $dir ) ) {
				wp_mkdir_p( $dir );
			}
			if ( false === file_put_contents( trailingslashit( $dir ) . $filename, $html ) ) {
				return false;
			}
			$this->snapshot_hashes[ $sha ] = 'snapshots/' . $filename;
			$entry['status'] = 'saved';
		}
		$this->snapshot_manifest[] = $entry;
		return 'saved' === $entry['status'];
	}

	/** Extract <link rel="canonical" href>, or null. */
	public static function extract_canonical( $html ) {
		if ( preg_match( '/<link\b[^>]*rel=["\']canonical["\'][^>]*>/i', (string) $html, $tag ) && preg_match( '/href=["\']([^"\']+)["\']/i', $tag[0], $href ) ) {
			return html_entity_decode( $href[1], ENT_QUOTES );
		}
		return null;
	}

	/** Compare URLs ignoring scheme, trailing slash and fragment. */
	public static function same_url( $a, $b ) {
		$norm = function ( $url ) {
			$url = preg_replace( '/#.*$/', '', strtolower( (string) $url ) );
			$url = preg_replace( '#^https?://#', '', $url );
			return rtrim( $url, '/' );
		};
		return $norm( $a ) === $norm( $b );
	}

	private function write_snapshot_manifest() {
		if ( empty( $this->snapshot_manifest ) ) {
			return;
		}
		$dir = trailingslashit( $this->export_dir ) . 'snapshots';
		if ( ! file_exists( $dir ) ) {
			wp_mkdir_p( $dir );
		}
		$manifest = array(
			'schema_version'     => 1,
			'viewports_required' => array( 390, 768, 1440 ),
			'screenshots'        => 'requires_headless_renderer',
			'note'               => 'PHP fetches server HTML only; full-page PNGs at each width need a headless browser run beside the exporter.',
			'snapshots'          => $this->snapshot_manifest,
		);
		file_put_contents( trailingslashit( $dir ) . 'manifest.json', wp_json_encode( $manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES ) );
	}

	/**
	 * Resolve the normalized snapshot mode with legacy boolean compatibility.
	 *
	 * @return string One of bounded, off, or all.
	 */
	private function get_html_snapshot_mode() {
		$mode = isset( $this->settings['html_snapshot_mode'] ) ? $this->settings['html_snapshot_mode'] : '';
		if ( in_array( $mode, array( 'bounded', 'off', 'all' ), true ) ) {
			return $mode;
		}

		return empty( $this->settings['include_html_snapshots'] ) ? 'off' : 'bounded';
	}

	/**
	 * Flatten public content records into a stable candidate list.
	 *
	 * @param array $content_data Exported content groups.
	 * @return array Snapshot candidates.
	 */
	private function flatten_snapshot_candidates( array $content_data ) {
		$candidates = array();

		foreach ( array( 'posts', 'pages' ) as $group ) {
			if ( ! empty( $content_data[ $group ] ) && is_array( $content_data[ $group ] ) ) {
				$candidates = array_merge( $candidates, $content_data[ $group ] );
			}
		}

		if ( ! empty( $content_data['custom_post_types'] ) && is_array( $content_data['custom_post_types'] ) ) {
			$custom_post_types = $content_data['custom_post_types'];
			ksort( $custom_post_types );
			foreach ( $custom_post_types as $items ) {
				if ( is_array( $items ) ) {
					$candidates = array_merge( $candidates, $items );
				}
			}
		}

		return array_values(
			array_filter(
				$candidates,
				function ( $candidate ) {
					return is_array( $candidate ) && ! empty( $candidate['id'] );
				}
			)
		);
	}

	/**
	 * Select representative source routes without making target decisions.
	 *
	 * The front/posts pages, every public content type, distinct source template
	 * families, and content with form/shortcode markers are preferred. Remaining
	 * capacity is filled deterministically up to MAX_HTML_SNAPSHOTS.
	 *
	 * @param array $content_data Exported content groups.
	 * @return array Bounded snapshot candidates.
	 */
	private function select_bounded_snapshot_candidates( array $content_data ) {
		$candidates = $this->flatten_snapshot_candidates( $content_data );
		$by_id      = array();
		$selected   = array();
		$seen       = array();

		foreach ( $candidates as $candidate ) {
			$by_id[ (int) $candidate['id'] ] = $candidate;
		}

		$add = function ( $candidate ) use ( &$selected, &$seen ) {
			$id = isset( $candidate['id'] ) ? (int) $candidate['id'] : 0;
			if ( $id < 1 || isset( $seen[ $id ] ) || count( $selected ) >= self::MAX_HTML_SNAPSHOTS ) {
				return;
			}
			$seen[ $id ] = true;
			$selected[]  = $candidate;
		};

		foreach ( array( 'page_on_front', 'page_for_posts' ) as $option ) {
			$id = (int) get_option( $option, 0 );
			if ( isset( $by_id[ $id ] ) ) {
				$add( $by_id[ $id ] );
			}
		}

		$by_type = array();
		foreach ( $candidates as $candidate ) {
			$type = isset( $candidate['type'] ) ? (string) $candidate['type'] : '';
			if ( ! isset( $by_type[ $type ] ) ) {
				$by_type[ $type ] = $candidate;
			}
		}
		ksort( $by_type );
		foreach ( $by_type as $candidate ) {
			$add( $candidate );
		}

		$by_template = array();
		foreach ( $candidates as $candidate ) {
			$type     = isset( $candidate['type'] ) ? (string) $candidate['type'] : '';
			$template = isset( $candidate['template'] ) ? (string) $candidate['template'] : 'default';
			$key      = $type . '|' . $template;
			if ( ! isset( $by_template[ $key ] ) ) {
				$by_template[ $key ] = $candidate;
			}
		}
		ksort( $by_template );
		foreach ( $by_template as $candidate ) {
			$add( $candidate );
		}

		foreach ( $candidates as $candidate ) {
			$html = isset( $candidate['raw_html'] ) ? (string) $candidate['raw_html'] : '';
			if ( false !== stripos( $html, '<form' ) || preg_match( '/\[[a-z][a-z0-9_-]*(?:\s|\])/i', $html ) ) {
				$add( $candidate );
			}
		}

		usort(
			$candidates,
			function ( $left, $right ) {
				$left_key  = sprintf( '%s|%010d|%s', isset( $left['type'] ) ? $left['type'] : '', (int) $left['id'], isset( $left['slug'] ) ? $left['slug'] : '' );
				$right_key = sprintf( '%s|%010d|%s', isset( $right['type'] ) ? $right['type'] : '', (int) $right['id'], isset( $right['slug'] ) ? $right['slug'] : '' );
				return strcmp( $left_key, $right_key );
			}
		);
		foreach ( $candidates as $candidate ) {
			$add( $candidate );
		}

		return $selected;
	}

	/**
	 * Generate HTML snapshot for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return bool True on success, false on failure.
	 */
	private function generate_html_snapshot( $post ) {
		// Create snapshots directory if it doesn't exist
		$snapshots_dir = trailingslashit( $this->export_dir ) . 'snapshots';
		if ( ! file_exists( $snapshots_dir ) ) {
			wp_mkdir_p( $snapshots_dir );
		}

		// Generate filename
		$filename = sanitize_file_name( $post->post_name ) . '.html';
		$filepath = trailingslashit( $snapshots_dir ) . $filename;

		// Try to fetch rendered HTML via wp_remote_get
		$html = $this->fetch_rendered_html( $post );

		// A failed public request is structured as unavailable evidence. The
		// exporter never re-executes a theme template to manufacture a snapshot.
		if ( false === $html ) {
			error_log( sprintf(
				'Moltex Exporter: Failed to generate HTML snapshot for post %d (%s)',
				$post->ID,
				$post->post_name
			) );
			return false;
		}

		// Save through the canonical/duplicate guard (S1).
		$result = $this->save_snapshot( $filename, (string) get_permalink( $post->ID ), $html, 'detail:' . $post->post_type, true, (int) $post->ID );

		if ( false === $result ) {
			error_log( sprintf(
				'Moltex Exporter: Failed to write HTML snapshot file for post %d (%s)',
				$post->ID,
				$post->post_name
			) );
			return false;
		}

		return true;
	}

	/**
	 * Fetch rendered HTML via wp_remote_get.
	 *
	 * @param WP_Post $post Post object.
	 * @return string|false HTML content or false on failure.
	 */
	private function fetch_rendered_html( $post ) {
		// Get the permalink
		$permalink = get_permalink( $post->ID );

		if ( ! $permalink ) {
			return false;
		}

		// Skip if post is not published (private posts may not be accessible)
		if ( 'publish' !== $post->post_status ) {
			return false;
		}

		// Make remote request
		try {
			$response = Moltex_Exporter_Public_Http_Policy::get( $permalink, array(
			'timeout'     => 30,
			'redirection' => 5,
			'headers'     => array(
				'User-Agent' => 'Moltex-Exporter/1.0',
			),
			) );
		} catch ( InvalidArgumentException $error ) {
			error_log( sprintf(
				'Moltex Exporter: unsafe snapshot URL for post %d: %s',
				$post->ID,
				$error->getMessage()
			) );
			return false;
		}

		// Check for errors
		if ( is_wp_error( $response ) ) {
			error_log( sprintf(
				'Moltex Exporter: wp_remote_get error for post %d: %s',
				$post->ID,
				$response->get_error_message()
			) );
			return false;
		}

		// Check response code
		$response_code = wp_remote_retrieve_response_code( $response );
		if ( 200 !== $response_code ) {
			error_log( sprintf(
				'Moltex Exporter: HTTP %d response for post %d (%s)',
				$response_code,
				$post->ID,
				$permalink
			) );
			return false;
		}

		// Get body
		$html = wp_remote_retrieve_body( $response );

		if ( empty( $html ) ) {
			return false;
		}

		return $html;
	}

}
