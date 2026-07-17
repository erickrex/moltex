<?php
/**
 * Assets Scanner Class
 *
 * Captures all enqueued scripts and styles, including their dependencies,
 * versions, load positions, and source identification. Copies local assets
 * to the export directory and notes external CDN resources.
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Assets Scanner Class
 */
class Moltex_Exporter_Assets_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Assets directory for copied files.
	 *
	 * @var string
	 */
	private $assets_dir = '';

	/**
	 * Site URL for identifying local assets.
	 *
	 * @var string
	 */
	private $site_url = '';

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->assets_dir = $this->export_dir . '/assets';
		$this->site_url   = get_site_url();
	}

	/**
	 * Run the assets scan.
	 *
	 * @return array Scan results.
	 */
	public function scan() {
		$results = array(
			'success' => true,
			'message' => 'Assets scan completed',
			'data'    => array(),
		);

		try {
			// Create assets directories.
			$this->create_assets_directories();

			// Capture only public frontend assets. The exporter runs in an admin
			// request, so the existing queues may contain editor and dashboard
			// assets that are not evidence for the public site.
			$all_assets = $this->capture_frontend_assets();

			// Copy local files.
			$copied_files = $this->copy_local_assets( $all_assets );

			// Build the complete registry.
			$registry = $this->build_registry( $all_assets, $copied_files );

			$results['data'] = array(
				'total_scripts'      => count( $all_assets['scripts'] ),
				'total_styles'       => count( $all_assets['styles'] ),
				'local_files_copied' => count( $copied_files ),
				'cdn_resources'      => $this->count_cdn_resources( $all_assets ),
			);

		} catch ( Exception $e ) {
			$results['success'] = false;
			$results['message'] = 'Assets scan failed: ' . $e->getMessage();
		}

		return $results;
	}

	/**
	 * Create assets directories.
	 */
	private function create_assets_directories() {
		$dirs = array(
			$this->assets_dir,
			$this->assets_dir . '/js',
			$this->assets_dir . '/css',
		);

		foreach ( $dirs as $dir ) {
			if ( ! file_exists( $dir ) ) {
				wp_mkdir_p( $dir );
			}
		}
	}

	/**
	 * Capture frontend enqueued assets.
	 *
	 * @return array Frontend assets.
	 */
	private function capture_frontend_assets() {
		global $wp_scripts, $wp_styles;

		$original_scripts     = $wp_scripts;
		$original_styles      = $wp_styles;
		$original_script_queue = $wp_scripts instanceof WP_Scripts ? $wp_scripts->queue : array();
		$original_style_queue  = $wp_styles instanceof WP_Styles ? $wp_styles->queue : array();

		if ( $wp_scripts instanceof WP_Scripts ) {
			$wp_scripts->queue = array();
		}

		if ( $wp_styles instanceof WP_Styles ) {
			$wp_styles->queue = array();
		}

		try {
			// The enqueue hook is the supported boundary for public assets. Firing
			// wp_head here would render arbitrary frontend markup into the AJAX
			// export response and introduce unrelated side effects.
			do_action( 'wp_enqueue_scripts' );

			return array(
				'scripts' => $this->get_enqueued_scripts( $wp_scripts, 'frontend' ),
				'styles'  => $this->get_enqueued_styles( $wp_styles, 'frontend' ),
			);
		} finally {
			if ( $original_scripts instanceof WP_Scripts ) {
				$original_scripts->queue = $original_script_queue;
			}

			if ( $original_styles instanceof WP_Styles ) {
				$original_styles->queue = $original_style_queue;
			}

			$wp_scripts = $original_scripts;
			$wp_styles  = $original_styles;
		}
	}

	/**
	 * Get enqueued scripts information.
	 *
	 * @param WP_Scripts $wp_scripts WordPress scripts object.
	 * @param string     $context Context (frontend or admin).
	 * @return array Scripts information.
	 */
	private function get_enqueued_scripts( $wp_scripts, $context ) {
		if ( ! $wp_scripts instanceof WP_Scripts ) {
			return array();
		}

		$scripts = array();

		$handles = $this->resolve_dependency_handles( $wp_scripts->registered, $wp_scripts->queue );

		foreach ( $handles as $handle ) {
			$script = $wp_scripts->registered[ $handle ];
			$script_info = array(
				'handle'       => $handle,
				'src'          => $this->normalize_url( $script->src ),
				'dependencies' => $script->deps,
				'version'      => $script->ver ? $script->ver : 'none',
				'in_footer'    => isset( $script->extra['group'] ) && $script->extra['group'] === 1,
				'context'      => $context,
				'enqueued'     => true,
				'source'       => $this->identify_asset_source( $script->src ),
				'is_local'     => $this->is_local_asset( $script->src ),
				'inline'       => array(),
			);

			// Capture inline scripts.
			if ( isset( $script->extra['data'] ) ) {
				$script_info['inline'][] = array(
					'position' => 'before',
					'data'     => $script->extra['data'],
				);
			}

			if ( isset( $script->extra['after'] ) && is_array( $script->extra['after'] ) ) {
				foreach ( $script->extra['after'] as $after_script ) {
					$script_info['inline'][] = array(
						'position' => 'after',
						'data'     => $after_script,
					);
				}
			}

			// Add localized data.
			if ( isset( $wp_scripts->registered[ $handle ]->extra['data'] ) ) {
				$script_info['localized'] = $wp_scripts->registered[ $handle ]->extra['data'];
			}

			$scripts[ $handle ] = $script_info;
		}

		return $scripts;
	}

	/**
	 * Get enqueued styles information.
	 *
	 * @param WP_Styles $wp_styles WordPress styles object.
	 * @param string    $context Context (frontend or admin).
	 * @return array Styles information.
	 */
	private function get_enqueued_styles( $wp_styles, $context ) {
		if ( ! $wp_styles instanceof WP_Styles ) {
			return array();
		}

		$styles = array();

		$handles = $this->resolve_dependency_handles( $wp_styles->registered, $wp_styles->queue );

		foreach ( $handles as $handle ) {
			$style = $wp_styles->registered[ $handle ];
			$style_info = array(
				'handle'       => $handle,
				'src'          => $this->normalize_url( $style->src ),
				'dependencies' => $style->deps,
				'version'      => $style->ver ? $style->ver : 'none',
				'media'        => $style->args,
				'context'      => $context,
				'enqueued'     => true,
				'source'       => $this->identify_asset_source( $style->src ),
				'is_local'     => $this->is_local_asset( $style->src ),
				'inline'       => array(),
			);

			// Capture inline styles.
			if ( isset( $style->extra['after'] ) && is_array( $style->extra['after'] ) ) {
				foreach ( $style->extra['after'] as $inline_css ) {
					$style_info['inline'][] = $inline_css;
				}
			}

			$styles[ $handle ] = $style_info;
		}

		return $styles;
	}

	/**
	 * Resolve queued handles and their registered dependency closure.
	 *
	 * Dependencies are returned before their consumers so the registry and
	 * generated load order remain deterministic and usable.
	 *
	 * @param array $registered Registered WordPress dependencies.
	 * @param array $queue Root handles queued for the public request.
	 * @return string[] Selected handles in dependency order.
	 */
	private function resolve_dependency_handles( array $registered, array $queue ) {
		$selected = array();
		$visiting = array();

		foreach ( array_values( array_unique( $queue ) ) as $handle ) {
			$this->collect_dependency_handle( $handle, $registered, $selected, $visiting );
		}

		return array_keys( $selected );
	}

	/**
	 * Add one registered handle and its dependencies to the selected set.
	 *
	 * @param string $handle Handle to collect.
	 * @param array  $registered Registered WordPress dependencies.
	 * @param array  $selected Selected handle set.
	 * @param array  $visiting Handles currently being traversed.
	 * @return void
	 */
	private function collect_dependency_handle( $handle, array $registered, array &$selected, array &$visiting ) {
		if ( isset( $selected[ $handle ] ) || isset( $visiting[ $handle ] ) || ! isset( $registered[ $handle ] ) ) {
			return;
		}

		$visiting[ $handle ] = true;
		$dependency          = $registered[ $handle ];
		$dependencies        = isset( $dependency->deps ) && is_array( $dependency->deps ) ? $dependency->deps : array();

		foreach ( $dependencies as $dependency_handle ) {
			$this->collect_dependency_handle( $dependency_handle, $registered, $selected, $visiting );
		}

		unset( $visiting[ $handle ] );
		$selected[ $handle ] = true;
	}

	/**
	 * Normalize asset URL.
	 *
	 * @param string $url Asset URL.
	 * @return string Normalized URL.
	 */
	private function normalize_url( $url ) {
		if ( empty( $url ) ) {
			return '';
		}

		// Handle protocol-relative URLs.
		if ( strpos( $url, '//' ) === 0 ) {
			$url = 'https:' . $url;
		}

		// Handle relative URLs.
		if ( strpos( $url, '/' ) === 0 && strpos( $url, '//' ) !== 0 ) {
			$url = $this->site_url . $url;
		}

		return $url;
	}

	/**
	 * Check if asset is local (not from CDN).
	 *
	 * @param string $url Asset URL.
	 * @return bool True if local.
	 */
	private function is_local_asset( $url ) {
		if ( empty( $url ) ) {
			return false;
		}

		$normalized_url = $this->normalize_url( $url );
		$site_url       = trailingslashit( $this->site_url );

		return strpos( $normalized_url, $site_url ) === 0;
	}

	/**
	 * Identify the source of an asset.
	 *
	 * @param string $url Asset URL.
	 * @return array Source information.
	 */
	private function identify_asset_source( $url ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		if ( empty( $url ) ) {
			return $source;
		}

		$normalized_url = $this->normalize_url( $url );

		// Check if it's a CDN.
		if ( ! $this->is_local_asset( $url ) ) {
			$source['type'] = 'cdn';
			$source['name'] = $this->extract_cdn_name( $normalized_url );
			return $source;
		}

		// Parse local path.
		$path = str_replace( $this->site_url, '', $normalized_url );
		$path = ltrim( $path, '/' );

		// Check if it's from WordPress core.
		if ( strpos( $path, 'wp-includes/' ) === 0 || strpos( $path, 'wp-admin/' ) === 0 ) {
			$source['type'] = 'core';
			$source['name'] = 'WordPress Core';
			return $source;
		}

		// Check if it's from a plugin.
		if ( strpos( $path, 'wp-content/plugins/' ) === 0 ) {
			$plugin_path = str_replace( 'wp-content/plugins/', '', $path );
			$parts       = explode( '/', $plugin_path );

			if ( ! empty( $parts[0] ) ) {
				$plugin_slug = $parts[0];
				$plugin_data = Moltex_Exporter_Source_Identifier::get_plugin_data( $plugin_slug );

				$source['type'] = 'plugin';
				$source['name'] = $plugin_data['name'];
				$source['slug'] = $plugin_slug;
			}
		} elseif ( strpos( $path, 'wp-content/themes/' ) === 0 ) {
			// Check if it's from a theme.
			$theme_path = str_replace( 'wp-content/themes/', '', $path );
			$parts      = explode( '/', $theme_path );

			if ( ! empty( $parts[0] ) ) {
				$theme_slug = $parts[0];
				$theme      = wp_get_theme( $theme_slug );

				$source['type'] = 'theme';
				$source['name'] = $theme->exists() ? $theme->get( 'Name' ) : ucwords( str_replace( array( '-', '_' ), ' ', $theme_slug ) );
				$source['slug'] = $theme_slug;
			}
		} elseif ( strpos( $path, 'wp-content/uploads/' ) === 0 ) {
			$source['type'] = 'uploads';
			$source['name'] = 'Uploads Directory';
		}

		return $source;
	}

	/**
	 * Extract CDN name from URL.
	 *
	 * @param string $url CDN URL.
	 * @return string CDN name.
	 */
	private function extract_cdn_name( $url ) {
		$parsed = wp_parse_url( $url );

		if ( ! isset( $parsed['host'] ) ) {
			return 'External CDN';
		}

		$host = $parsed['host'];

		// Common CDN patterns.
		$cdn_patterns = array(
			'googleapis.com'    => 'Google CDN',
			'cloudflare.com'    => 'Cloudflare',
			'jsdelivr.net'      => 'jsDelivr',
			'unpkg.com'         => 'unpkg',
			'cdnjs.cloudflare'  => 'cdnjs',
			'bootstrapcdn.com'  => 'Bootstrap CDN',
			'fontawesome.com'   => 'Font Awesome CDN',
			'jquery.com'        => 'jQuery CDN',
			'maxcdn.com'        => 'MaxCDN',
			'akamaihd.net'      => 'Akamai',
			'cloudfront.net'    => 'Amazon CloudFront',
		);

		foreach ( $cdn_patterns as $pattern => $name ) {
			if ( strpos( $host, $pattern ) !== false ) {
				return $name;
			}
		}

		return $host;
	}

	/**
	 * Copy local assets to export directory.
	 *
	 * @param array $assets All assets.
	 * @return array Copied files information.
	 */
	private function copy_local_assets( $assets ) {
		$copied_files = array();

		// Copy scripts.
		foreach ( $assets['scripts'] as $handle => $script ) {
			if ( $script['enqueued'] && $script['is_local'] && ! empty( $script['src'] ) ) {
				$copied = $this->copy_asset_file( $script['src'], 'js' );
				if ( $copied ) {
					$copied_files[] = $copied;
				}
			}
		}

		// Copy styles.
		foreach ( $assets['styles'] as $handle => $style ) {
			if ( $style['enqueued'] && $style['is_local'] && ! empty( $style['src'] ) ) {
				$copied = $this->copy_asset_file( $style['src'], 'css' );
				if ( $copied ) {
					$copied_files[] = $copied;
				}
			}
		}

		return $copied_files;
	}

	/**
	 * Copy a single asset file.
	 *
	 * @param string $url Asset URL.
	 * @param string $type Asset type (js or css).
	 * @return array|false Copied file info or false on failure.
	 */
	private function copy_asset_file( $url, $type ) {
		$normalized_url = $this->normalize_url( $url );
		$path           = str_replace( $this->site_url, '', $normalized_url );
		$path           = ltrim( $path, '/' );

		// Remove query string.
		$path_parts = explode( '?', $path );
		$path       = $path_parts[0];

		// Get the source file path.
		$source_file = ABSPATH . $path;

		if ( ! file_exists( $source_file ) || ! is_readable( $source_file ) ) {
			return false;
		}

		// Generate destination filename.
		$filename = basename( $path );
		$dest_dir = $this->assets_dir . '/' . $type;

		// Handle duplicate filenames by adding source identifier.
		$dest_file = $dest_dir . '/' . $filename;
		$counter   = 1;

		while ( file_exists( $dest_file ) ) {
			$file_parts = pathinfo( $filename );
			$new_name   = $file_parts['filename'] . '-' . $counter . '.' . $file_parts['extension'];
			$dest_file  = $dest_dir . '/' . $new_name;
			$counter++;
		}

		// Copy the file.
		$copied = copy( $source_file, $dest_file );

		if ( ! $copied ) {
			return false;
		}

		return array(
			'original_url' => $url,
			'source_path'  => $path,
			'dest_path'    => 'assets/' . $type . '/' . basename( $dest_file ),
			'size'         => filesize( $dest_file ),
		);
	}

	/**
	 * Count CDN resources.
	 *
	 * @param array $assets All assets.
	 * @return int CDN resource count.
	 */
	private function count_cdn_resources( $assets ) {
		$count = 0;

		foreach ( $assets['scripts'] as $script ) {
			if ( ! $script['is_local'] ) {
				$count++;
			}
		}

		foreach ( $assets['styles'] as $style ) {
			if ( ! $style['is_local'] ) {
				$count++;
			}
		}

		return $count;
	}

	/**
	 * Build the complete registry.
	 *
	 * @param array $assets All assets.
	 * @param array $copied_files Copied files information.
	 * @return array Complete registry.
	 */
	private function build_registry( $assets, $copied_files ) {
		$registry = array(
			'schema_version' => 1,
			'generated_at'   => current_time( 'mysql', true ),
			'summary'        => array(
				'total_scripts'      => count( $assets['scripts'] ),
				'total_styles'       => count( $assets['styles'] ),
				'enqueued_scripts'   => $this->count_enqueued( $assets['scripts'] ),
				'enqueued_styles'    => $this->count_enqueued( $assets['styles'] ),
				'local_scripts'      => $this->count_local( $assets['scripts'] ),
				'local_styles'       => $this->count_local( $assets['styles'] ),
				'cdn_scripts'        => $this->count_cdn( $assets['scripts'] ),
				'cdn_styles'         => $this->count_cdn( $assets['styles'] ),
				'copied_files'       => count( $copied_files ),
			),
			'scripts'        => $this->sort_by_dependencies( $assets['scripts'] ),
			'styles'         => $this->sort_by_dependencies( $assets['styles'] ),
			'cdn_resources'  => $this->extract_cdn_resources( $assets ),
			'copied_files'   => $copied_files,
			'load_order'     => $this->generate_load_order( $assets ),
		);

		return $registry;
	}

	/**
	 * Count enqueued assets.
	 *
	 * @param array $assets Assets array.
	 * @return int Count.
	 */
	private function count_enqueued( $assets ) {
		$count = 0;
		foreach ( $assets as $asset ) {
			if ( $asset['enqueued'] ) {
				$count++;
			}
		}
		return $count;
	}

	/**
	 * Count local assets.
	 *
	 * @param array $assets Assets array.
	 * @return int Count.
	 */
	private function count_local( $assets ) {
		$count = 0;
		foreach ( $assets as $asset ) {
			if ( $asset['is_local'] ) {
				$count++;
			}
		}
		return $count;
	}

	/**
	 * Count CDN assets.
	 *
	 * @param array $assets Assets array.
	 * @return int Count.
	 */
	private function count_cdn( $assets ) {
		$count = 0;
		foreach ( $assets as $asset ) {
			if ( ! $asset['is_local'] ) {
				$count++;
			}
		}
		return $count;
	}

	/**
	 * Sort assets by dependencies (topological sort).
	 *
	 * @param array $assets Assets to sort.
	 * @return array Sorted assets.
	 */
	private function sort_by_dependencies( $assets ) {
		// For now, just return as array values (not keyed by handle).
		// A full topological sort could be implemented if needed.
		return array_values( $assets );
	}

	/**
	 * Extract CDN resources separately.
	 *
	 * @param array $assets All assets.
	 * @return array CDN resources.
	 */
	private function extract_cdn_resources( $assets ) {
		$cdn_resources = array(
			'scripts' => array(),
			'styles'  => array(),
		);

		foreach ( $assets['scripts'] as $script ) {
			if ( ! $script['is_local'] ) {
				$cdn_resources['scripts'][] = array(
					'handle'  => $script['handle'],
					'src'     => $script['src'],
					'version' => $script['version'],
					'cdn'     => $script['source']['name'],
				);
			}
		}

		foreach ( $assets['styles'] as $style ) {
			if ( ! $style['is_local'] ) {
				$cdn_resources['styles'][] = array(
					'handle'  => $style['handle'],
					'src'     => $style['src'],
					'version' => $style['version'],
					'cdn'     => $style['source']['name'],
				);
			}
		}

		return $cdn_resources;
	}

	/**
	 * Generate load order documentation.
	 *
	 * @param array $assets All assets.
	 * @return array Load order information.
	 */
	private function generate_load_order( $assets ) {
		$load_order = array(
			'header_scripts' => array(),
			'footer_scripts' => array(),
			'styles'         => array(),
		);

		foreach ( $assets['scripts'] as $script ) {
			if ( ! $script['enqueued'] ) {
				continue;
			}

			$position = $script['in_footer'] ? 'footer_scripts' : 'header_scripts';
			$load_order[ $position ][] = array(
				'handle'       => $script['handle'],
				'dependencies' => $script['dependencies'],
				'source'       => $script['source']['name'],
			);
		}

		foreach ( $assets['styles'] as $style ) {
			if ( ! $style['enqueued'] ) {
				continue;
			}

			$load_order['styles'][] = array(
				'handle'       => $style['handle'],
				'dependencies' => $style['dependencies'],
				'media'        => $style['media'],
				'source'       => $style['source']['name'],
			);
		}

		return $load_order;
	}


}
