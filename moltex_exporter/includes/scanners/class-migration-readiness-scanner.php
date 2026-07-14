<?php
/**
 * ChatGPT Sites migration readiness scanner.
 *
 * Rejects site classes that are deliberately outside the initial local
 * complete-migration scope. It does not claim that unlisted plugins are
 * compatible; unknown behavior remains subject to Codex review.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

class Moltex_Exporter_Migration_Readiness_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Plugin families that require transactional or account-heavy behavior.
	 *
	 * @var array
	 */
	private $blocked_plugin_families = array(
		'woocommerce/'              => array( 'ecommerce', 'WooCommerce' ),
		'easy-digital-downloads/'   => array( 'ecommerce', 'Easy Digital Downloads' ),
		'memberpress/'              => array( 'membership', 'MemberPress' ),
		'paid-memberships-pro/'     => array( 'membership', 'Paid Memberships Pro' ),
		'restrict-content-pro/'     => array( 'membership', 'Restrict Content Pro' ),
		'buddypress/'               => array( 'community', 'BuddyPress' ),
		'bbpress/'                  => array( 'community', 'bbPress' ),
		'sfwd-lms/'                 => array( 'learning_management', 'LearnDash' ),
		'lifterlms/'                => array( 'learning_management', 'LifterLMS' ),
		'tutor/'                    => array( 'learning_management', 'Tutor LMS' ),
		'bookly-responsive-appointment-booking-tool/' => array( 'booking', 'Bookly' ),
	);

	/**
	 * Scan the active site for hard blockers.
	 *
	 * @return array
	 */
	public function scan() {
		$blockers = array();
		$active_plugins = get_option( 'active_plugins', array() );

		foreach ( $active_plugins as $plugin_file ) {
			foreach ( $this->blocked_plugin_families as $prefix => $definition ) {
				if ( 0 !== strpos( $plugin_file, $prefix ) ) {
					continue;
				}
				$blockers[] = array(
					'code'       => 'unsupported_plugin_family',
					'category'   => $definition[0],
					'plugin'     => $definition[1],
					'plugin_file' => $plugin_file,
					'message'    => sprintf( '%s is outside the initial basic ChatGPT Sites migration scope.', $definition[1] ),
				);
			}
		}

		if ( is_multisite() ) {
			$blockers[] = array(
				'code'     => 'wordpress_multisite',
				'category' => 'multisite',
				'message'  => 'WordPress multisite is outside the initial complete-migration scope.',
			);
		}

		$completeness = isset( $this->context['content']['completeness'] )
			? $this->context['content']['completeness']
			: array();
		if ( isset( $completeness['complete'] ) && ! $completeness['complete'] ) {
			$blockers[] = array(
				'code'     => 'incomplete_content_export',
				'category' => 'content_volume',
				'message'  => 'The exporter did not export every eligible content item. Review export_completeness.json.',
			);
		}

		return array(
			'target'        => 'chatgpt_sites',
			'scope'         => 'basic_content_sites',
			'eligible'      => empty( $blockers ),
			'blockers'      => $blockers,
			'manual_review' => array(
				'forms and submission destinations',
				'custom shortcodes and PHP hooks',
				'external APIs and webhooks',
				'authentication and private content',
				'SEO, redirects, accessibility, and visual parity',
			),
		);
	}
}
