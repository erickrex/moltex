<?php
/**
 * Admin Page Template
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

$defaults = array(
	'export_mode'              => 'complete',
	'complete_export_max_items' => 5000,
	'include_private_content'  => false,
	'max_posts'                => 100,
	'max_pages'                => 50,
	'max_per_custom_post_type' => 50,
	'html_snapshot_mode'       => 'bounded',
	'include_html_snapshots'   => true,
	'batch_size'               => 50,
	'cleanup_after_hours'      => 24,
);
$defaults = array_merge( $defaults, Moltex_Exporter_Export_Policy::sanitize( array() ) );
$settings = get_option( 'moltex_settings', $defaults );
$settings['html_snapshot_mode'] = isset( $settings['html_snapshot_mode'] )
	? $settings['html_snapshot_mode']
	: ( empty( $settings['include_html_snapshots'] ) ? 'off' : 'bounded' );
$settings = wp_parse_args( $settings, $defaults );
$preflight = isset( $preflight ) && is_array( $preflight ) ? $preflight : array( 'ready' => false, 'blockers' => array( 'Preflight was unavailable.' ), 'warnings' => array() );
?>

<div class="wrap moltex-exporter-wrap">
	<h1><?php echo esc_html( 'Moltex Exporter' ); ?></h1>
	
	<div class="moltex-exporter-container">
		<div class="notice <?php echo $preflight['ready'] ? 'notice-success' : 'notice-error'; ?> inline">
			<p><strong><?php echo esc_html( $preflight['ready'] ? 'Export preflight passed.' : 'Export is blocked by preflight.' ); ?></strong></p>
			<?php if ( ! empty( $preflight['blockers'] ) ) : ?>
				<ul><?php foreach ( $preflight['blockers'] as $message ) : ?><li><?php echo esc_html( $message ); ?></li><?php endforeach; ?></ul>
			<?php endif; ?>
			<?php if ( ! empty( $preflight['warnings'] ) ) : ?>
				<ul><?php foreach ( $preflight['warnings'] as $message ) : ?><li><?php echo esc_html( $message ); ?></li><?php endforeach; ?></ul>
			<?php endif; ?>
		</div>
		<div class="moltex-exporter-header">
			<p class="moltex-exporter-tagline">
				<?php echo esc_html( 'Create a complete local migration blueprint for a verified Astro rebuild' ); ?>
			</p>
			
			<p class="moltex-exporter-description">
				<?php
				echo esc_html(
					'This plugin exports the WordPress evidence needed to rebuild the site as a Git-managed Astro website. The bundle includes public content, media, theme evidence, plugin configuration, routes, SEO data, and a compatibility report. Credentials and sensitive user data are excluded.'
				);
				?>
			</p>
		</div>

		<!-- Collapsible Settings Section -->
		<div class="moltex-exporter-settings-section">
			<button type="button" id="moltex-settings-toggle" class="button" style="margin-bottom: 10px;">
				<?php echo esc_html( 'Settings' ); ?>
			</button>

			<div id="moltex-settings-panel" style="display: none; background: #fff; border: 1px solid #ccd0d4; padding: 15px; margin-bottom: 20px;">
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row"><label for="moltex-export-mode"><?php echo esc_html( 'Export Mode' ); ?></label></th>
						<td>
							<select id="moltex-export-mode">
								<option value="complete" <?php selected( $settings['export_mode'], 'complete' ); ?>><?php echo esc_html( 'Complete migration' ); ?></option>
								<option value="discovery" <?php selected( $settings['export_mode'], 'discovery' ); ?>><?php echo esc_html( 'Discovery sample' ); ?></option>
							</select>
							<p class="description"><?php echo esc_html( 'Complete mode exports every supported public content item and records proof of completeness.' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-complete-ceiling"><?php echo esc_html( 'Complete Export Ceiling' ); ?></label></th>
						<td>
							<input type="number" id="moltex-complete-ceiling" value="<?php echo esc_attr( $settings['complete_export_max_items'] ); ?>" min="1" max="50000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum supported items per post type for the initial basic-site workflow (default: 5000).' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><?php echo esc_html( 'Private Content' ); ?></th>
						<td>
							<label><input type="checkbox" id="moltex-private-content" value="1" <?php checked( $settings['include_private_content'], true ); ?> /> <?php echo esc_html( 'Include private posts and pages' ); ?></label>
							<p class="description"><?php echo esc_html( 'Leave disabled for public Sites migrations to avoid accidental disclosure.' ); ?></p>
						</td>
					</tr>
					<tr class="moltex-discovery-setting">
						<th scope="row">
							<label for="moltex-max-posts"><?php echo esc_html( 'Max Posts' ); ?></label>
						</th>
						<td>
							<input type="number" id="moltex-max-posts" value="<?php echo esc_attr( $settings['max_posts'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of posts to export (default: 100)' ); ?></p>
						</td>
					</tr>
					<tr class="moltex-discovery-setting">
						<th scope="row">
							<label for="moltex-max-pages"><?php echo esc_html( 'Max Pages' ); ?></label>
						</th>
						<td>
							<input type="number" id="moltex-max-pages" value="<?php echo esc_attr( $settings['max_pages'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of pages to export (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr class="moltex-discovery-setting">
						<th scope="row">
							<label for="moltex-max-cpt"><?php echo esc_html( 'Max per Custom Post Type' ); ?></label>
						</th>
						<td>
							<input type="number" id="moltex-max-cpt" value="<?php echo esc_attr( $settings['max_per_custom_post_type'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of items to export per custom post type (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="moltex-html-snapshot-mode"><?php echo esc_html( 'HTML Snapshot Evidence' ); ?></label>
						</th>
						<td>
							<select id="moltex-html-snapshot-mode">
								<option value="bounded" <?php selected( $settings['html_snapshot_mode'], 'bounded' ); ?>><?php echo esc_html( 'Bounded representative set (recommended)' ); ?></option>
								<option value="off" <?php selected( $settings['html_snapshot_mode'], 'off' ); ?>><?php echo esc_html( 'Off' ); ?></option>
								<option value="all" <?php selected( $settings['html_snapshot_mode'], 'all' ); ?>><?php echo esc_html( 'All content (large diagnostic export)' ); ?></option>
							</select>
							<p class="description"><?php echo esc_html( 'The recommended mode captures at most 12 representative public routes. All content can substantially increase export time and ZIP size.' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="moltex-batch-size"><?php echo esc_html( 'Batch Size' ); ?></label>
						</th>
						<td>
							<input type="number" id="moltex-batch-size" value="<?php echo esc_attr( $settings['batch_size'] ); ?>" min="10" max="500" class="small-text" />
							<p class="description"><?php echo esc_html( 'Batch size for processing large datasets (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="moltex-cleanup-hours"><?php echo esc_html( 'Cleanup After (Hours)' ); ?></label>
						</th>
						<td>
							<input type="number" id="moltex-cleanup-hours" value="<?php echo esc_attr( $settings['cleanup_after_hours'] ); ?>" min="1" max="168" class="small-text" />
							<p class="description"><?php echo esc_html( 'Automatically delete old artifacts after this many hours (default: 24)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-media-acquisition"><?php echo esc_html( 'Media Files' ); ?></label></th>
						<td>
							<select id="moltex-media-acquisition">
								<option value="bundle_all" <?php selected( $settings['media_acquisition'], 'bundle_all' ); ?>><?php echo esc_html( 'Bundle every referenced original (recommended)' ); ?></option>
								<option value="featured_only" <?php selected( $settings['media_acquisition'], 'featured_only' ); ?>><?php echo esc_html( 'Bundle only featured GeoDirectory images (defer gallery files)' ); ?></option>
							</select>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-part-max-bytes"><?php echo esc_html( 'Archive Part Size (bytes)' ); ?></label></th>
						<td>
							<input type="number" id="moltex-part-max-bytes" value="<?php echo esc_attr( $settings['part_max_bytes'] ); ?>" min="<?php echo esc_attr( Moltex_Exporter_Export_Policy::MIN_PART_MAX_BYTES ); ?>" max="<?php echo esc_attr( Moltex_Exporter_Export_Policy::MAX_PART_MAX_BYTES ); ?>" class="regular-text" />
							<p class="description"><?php echo esc_html( 'Media is split into parts no larger than this (default: 24 MiB).' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-geodir-include-fields"><?php echo esc_html( 'Include Excluded GeoDirectory Fields' ); ?></label></th>
						<td>
							<input type="text" id="moltex-geodir-include-fields" value="<?php echo esc_attr( implode( ', ', (array) $settings['geodirectory_include_fields'] ) ); ?>" class="regular-text" />
							<p class="description"><?php echo esc_html( 'Comma-separated field keys whose values should be exported even though they are admin-only (for example featured, expire_date). Email values are never exported.' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-non-public-types"><?php echo esc_html( 'Include Non-Public Post Types' ); ?></label></th>
						<td>
							<input type="text" id="moltex-non-public-types" value="<?php echo esc_attr( implode( ', ', (array) $settings['include_non_public_post_types'] ) ); ?>" class="regular-text" />
							<p class="description"><?php echo esc_html( 'Comma-separated post type slugs (for example wp_story, popup_theme).' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><?php echo esc_html( 'Personal Data' ); ?></th>
						<td>
							<label><input type="checkbox" id="moltex-include-user-emails" <?php checked( ! empty( $settings['include_user_emails'] ) ); ?> /> <?php echo esc_html( 'Include listing owner email addresses' ); ?></label><br />
							<label><input type="checkbox" id="moltex-include-subscribers" <?php checked( ! empty( $settings['include_subscribers'] ) ); ?> /> <?php echo esc_html( 'Include newsletter subscribers' ); ?></label>
							<p class="description"><?php echo esc_html( 'Off by default. Only enable with a lawful basis to transfer this data.' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="moltex-production-origin"><?php echo esc_html( 'Production Origin' ); ?></label></th>
						<td>
							<input type="url" id="moltex-production-origin" class="regular-text" placeholder="https://www.example.com" value="<?php echo esc_attr( isset( $settings['production_origin'] ) ? $settings['production_origin'] : '' ); ?>" />
							<p class="description"><?php echo esc_html( 'Optional. The live domain when this site is a staging copy. Recorded as evidence only; URLs are not rewritten.' ); ?></p>
						</td>
					</tr>
				</table>

				<p>
					<button type="button" id="moltex-save-settings-btn" class="button button-primary">
						<?php echo esc_html( 'Save Settings' ); ?>
					</button>
					<span id="moltex-settings-status" style="margin-left: 10px;"></span>
				</p>
			</div>
		</div>

		<div class="moltex-exporter-actions">
			<h2><?php echo esc_html( 'Export blueprint' ); ?></h2>
			<p><?php echo esc_html( 'Package the selected public site evidence into a validated, downloadable ZIP.' ); ?></p>
			<button id="moltex-migrate-btn" class="button button-primary button-hero" <?php disabled( ! $preflight['ready'] ); ?>>
				<?php echo esc_html( 'Export blueprint' ); ?>
			</button>
		</div>

		<div id="moltex-progress-container" class="moltex-progress-container" style="display: none;">
			<div class="moltex-progress-bar">
				<div id="moltex-progress-fill" class="moltex-progress-fill"></div>
			</div>
			<p id="moltex-progress-stage" class="moltex-progress-stage"></p>
			<p id="moltex-progress-text" class="moltex-progress-text"></p>
		</div>

		<div id="moltex-success-container" class="moltex-success-container" style="display: none;">
			<p class="moltex-success-message">
				<?php echo esc_html( 'Blueprint artifacts created successfully!' ); ?>
			</p>
			<button id="moltex-download-btn" class="button button-primary">
				<?php echo esc_html( 'Download blueprint (.zip)' ); ?>
			</button>
		</div>

		<div id="moltex-warning-container" class="moltex-warning-container notice notice-warning" style="display: none; margin-top: 20px; padding: 10px 15px;">
			<p id="moltex-warning-message" class="moltex-warning-message"></p>
		</div>

		<div id="moltex-error-container" class="moltex-error-container notice notice-error" style="display: none; margin-top: 20px; padding: 10px 15px;">
			<p id="moltex-error-message" class="moltex-error-message"></p>
		</div>
	</div>
</div>
