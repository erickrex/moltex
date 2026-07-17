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
		$this->generate_selected_html_snapshots( $content_data );
		$content_data['completeness'] = $this->build_completeness_report( $content_data );

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
		
		// Exclude built-in types
		$exclude = array( 'post', 'page', 'attachment' );
		
		return array_diff( $all_post_types, $exclude );
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
		// Check if the geodir_cpt taxonomy exists
		if ( ! taxonomy_exists( 'geodir_cpt' ) ) {
			return false;
		}

		// Check if this post type is associated with geodir_cpt taxonomy
		$taxonomies = get_object_taxonomies( $post_type );
		return in_array( 'geodir_cpt', $taxonomies, true );
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
				// Extract address information
				$geodir_data['address'] = array(
					'street'   => isset( $detail_data['street'] ) ? $detail_data['street'] : '',
					'street2'  => isset( $detail_data['street2'] ) ? $detail_data['street2'] : '',
					'city'     => isset( $detail_data['city'] ) ? $detail_data['city'] : '',
					'region'   => isset( $detail_data['region'] ) ? $detail_data['region'] : '',
					'country'  => isset( $detail_data['country'] ) ? $detail_data['country'] : '',
					'zip'      => isset( $detail_data['zip'] ) ? $detail_data['zip'] : '',
					'postcode' => isset( $detail_data['postcode'] ) ? $detail_data['postcode'] : '',
				);

				// Extract geo coordinates
				$geodir_data['geo'] = array(
					'latitude'  => isset( $detail_data['latitude'] ) ? $detail_data['latitude'] : '',
					'longitude' => isset( $detail_data['longitude'] ) ? $detail_data['longitude'] : '',
				);

				// Store all other custom fields from the detail table
				$geodir_data['custom_fields'] = array();
				$exclude_fields = array( 'post_id', 'street', 'street2', 'city', 'region', 'country', 'zip', 'postcode', 'latitude', 'longitude' );
				
				foreach ( $detail_data as $key => $value ) {
					if ( ! in_array( $key, $exclude_fields, true ) ) {
						$geodir_data['custom_fields'][ $key ] = $value;
					}
				}
			}
		}

		// Get standard postmeta that GeoDirectory might use
		$geodir_meta_keys = array(
			'geodir_contact',
			'geodir_email',
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
			$geodir_data['postmeta'] = $postmeta;
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

		// GeoDirectory uses tables like geodir_gd_place_detail, geodir_gd_event_detail, etc.
		$table_name = $wpdb->prefix . 'geodir_' . $post_type . '_detail';

		// Check if table exists
		$table_exists = $wpdb->get_var(
			$wpdb->prepare(
				'SHOW TABLES LIKE %s',
				$table_name
			)
		);

		return $table_exists ? $table_name : null;
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

		// If remote fetch failed, try server-side template capture
		if ( false === $html ) {
			$html = $this->capture_template_output( $post );
		}

		// If we still don't have HTML, log error and return
		if ( false === $html ) {
			error_log( sprintf(
				'Moltex Exporter: Failed to generate HTML snapshot for post %d (%s)',
				$post->ID,
				$post->post_name
			) );
			return false;
		}

		// Save HTML to file
		$result = file_put_contents( $filepath, $html );

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
		$response = wp_remote_get( $permalink, array(
			'timeout'     => 30,
			'redirection' => 5,
			'sslverify'   => false, // Allow self-signed certificates in dev environments
			'headers'     => array(
				'User-Agent' => 'Moltex-Exporter/1.0',
			),
		) );

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

	/**
	 * Capture template output server-side as fallback.
	 *
	 * @param WP_Post $post Post object.
	 * @return string|false HTML content or false on failure.
	 */
	private function capture_template_output( $post ) {
		// This is a fallback method that captures the template output
		// by simulating the WordPress template hierarchy

		global $wp_query;

		// Save current query
		$original_query = $wp_query;

		// Create a new query for this specific post
		$wp_query = new WP_Query( array(
			'p'         => $post->ID,
			'post_type' => $post->post_type,
		) );

		// Set up post data
		if ( $wp_query->have_posts() ) {
			$wp_query->the_post();

			// Start output buffering
			ob_start();

			try {
				// Try to load the template
				// This will use the theme's template hierarchy
				if ( 'page' === $post->post_type ) {
					$template = get_page_template();
				} else {
					$template = get_single_template();
				}

				// If we found a template, include it
				if ( $template && file_exists( $template ) ) {
					include $template;
				} else {
					// No template found, return false
					ob_end_clean();
					wp_reset_postdata();
					$wp_query = $original_query;
					return false;
				}

				// Get the buffered content
				$html = ob_get_clean();

				// Reset post data
				wp_reset_postdata();

				// Restore original query
				$wp_query = $original_query;

				return $html;

			} catch ( Exception $e ) {
				// Clean buffer and restore state on error
				ob_end_clean();
				wp_reset_postdata();
				$wp_query = $original_query;

				error_log( sprintf(
					'Moltex Exporter: Template capture exception for post %d: %s',
					$post->ID,
					$e->getMessage()
				) );

				return false;
			}
		}

		// Restore original query
		$wp_query = $original_query;

		return false;
	}
}
