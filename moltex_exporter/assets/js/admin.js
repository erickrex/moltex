/**
 * Admin JavaScript for Moltex Exporter
 *
 * @package Moltex_Exporter
 */

(function($) {
	'use strict';

	$(document).ready(function() {
		const $settingsToggle = $('#moltex-settings-toggle');
		const $settingsPanel = $('#moltex-settings-panel');
		const $saveSettingsBtn = $('#moltex-save-settings-btn');
		const $settingsStatus = $('#moltex-settings-status');
		const $migrateBtn = $('#moltex-migrate-btn');
		const $progressContainer = $('#moltex-progress-container');
		const $progressFill = $('#moltex-progress-fill');
		const $progressText = $('#moltex-progress-text');
		const $progressStage = $('#moltex-progress-stage');
		const $successContainer = $('#moltex-success-container');
		const $downloadBtn = $('#moltex-download-btn');
		const $errorContainer = $('#moltex-error-container');
		const $errorMessage = $('#moltex-error-message');
		const $warningContainer = $('#moltex-warning-container');
		const $warningMessage = $('#moltex-warning-message');
		const $exportMode = $('#moltex-export-mode');
		const $screenshotTable = $('#moltex-screenshot-table tbody');
		const $screenshotStatus = $('#moltex-screenshot-status');

		let settingsOpen = false;

		function updateModeFields() {
			$('.moltex-discovery-setting').toggle($exportMode.val() === 'discovery');
		}
		$exportMode.on('change', updateModeFields);
		updateModeFields();

		$settingsToggle.on('click', function() {
			settingsOpen = !settingsOpen;
			$settingsPanel.slideToggle(200);
			$settingsToggle.text(settingsOpen ? 'Hide settings' : 'Settings');
		});

		$saveSettingsBtn.on('click', function() {
			$saveSettingsBtn.prop('disabled', true);
			$settingsStatus.text('Saving...').css('color', '');

			$.ajax({
				url: moltexExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'moltex_save_settings',
					nonce: moltexExporter.nonce,
					export_mode: $('#moltex-export-mode').val(),
					complete_export_max_items: $('#moltex-complete-ceiling').val(),
					include_private_content: $('#moltex-private-content').is(':checked') ? 1 : 0,
					max_posts: $('#moltex-max-posts').val(),
					max_pages: $('#moltex-max-pages').val(),
					max_per_custom_post_type: $('#moltex-max-cpt').val(),
					include_html_snapshots: $('#moltex-html-snapshots').is(':checked') ? 1 : 0,
					batch_size: $('#moltex-batch-size').val(),
					cleanup_after_hours: $('#moltex-cleanup-hours').val()
				},
				success: function(response) {
					$saveSettingsBtn.prop('disabled', false);
					if (response.success) {
						$settingsStatus.text('Settings saved.').css('color', '#46b450');
					} else {
						$settingsStatus.text(getResponseMessage(response, 'Error saving settings.')).css('color', '#dc3232');
					}
					setTimeout(function() { $settingsStatus.text(''); }, 3000);
				},
				error: function() {
					$saveSettingsBtn.prop('disabled', false);
					$settingsStatus.text('Error saving settings.').css('color', '#dc3232');
					setTimeout(function() { $settingsStatus.text(''); }, 3000);
				}
			});
		});

		function openScreenshotFrame($replaceRow) {
			if (!$replaceRow && $screenshotTable.find('.moltex-screenshot-row').length >= 10) {
				$screenshotStatus.text('At most ten screenshots are allowed.').css('color', '#dc3232');
				return;
			}
			const frame = wp.media({
				title: 'Select a reviewed PNG screenshot',
				button: { text: 'Use screenshot' },
				library: { type: 'image/png' },
				multiple: false
			});
			frame.on('select', function() {
				const attachment = frame.state().get('selection').first().toJSON();
				const name = attachment.filename || ('Attachment ' + attachment.id);
				if ($replaceRow) {
					$replaceRow.find('.moltex-screenshot-id').val(attachment.id);
					$replaceRow.find('.moltex-screenshot-name').text(name);
				} else {
					appendScreenshotRow(attachment.id, name, '/', 'desktop-1440x1200', 'home');
				}
			});
			frame.open();
		}

		$('#moltex-add-screenshot').on('click', function() {
			openScreenshotFrame(null);
		});

		$screenshotTable.on('click', '.moltex-replace-screenshot', function() {
			openScreenshotFrame($(this).closest('tr'));
		});

		$screenshotTable.on('click', '.moltex-remove-screenshot', function() {
			$(this).closest('tr').remove();
		});

		$('#moltex-save-screenshots').on('click', function() {
			const references = [];
			$screenshotTable.find('.moltex-screenshot-row').each(function() {
				const $row = $(this);
				references.push({
					attachment_id: parseInt($row.find('.moltex-screenshot-id').val(), 10),
					route: $row.find('.moltex-screenshot-route').val(),
					viewport: $row.find('.moltex-screenshot-viewport').val(),
					label: $row.find('.moltex-screenshot-label').val()
				});
			});
			$screenshotStatus.text('Saving...').css('color', '');
			$.ajax({
				url: moltexExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'moltex_save_reference_screenshots',
					nonce: moltexExporter.nonce,
					references: JSON.stringify(references)
				},
				success: function(response) {
					if (response.success) {
						$screenshotStatus.text('Screenshots saved. Reload to refresh preflight.').css('color', '#46b450');
					} else {
						$screenshotStatus.text(getResponseMessage(response, 'Could not save screenshots.')).css('color', '#dc3232');
					}
				},
				error: function(xhr) {
					$screenshotStatus.text(buildAjaxErrorMessage(xhr, 'request failed')).css('color', '#dc3232');
				}
			});
		});

		function appendScreenshotRow(id, name, route, viewport, label) {
			const $row = $('<tr>', { class: 'moltex-screenshot-row' });
			const $attachment = $('<td>');
			$attachment.append($('<input>', { type: 'hidden', class: 'moltex-screenshot-id', value: id }));
			$attachment.append($('<span>', { class: 'moltex-screenshot-name' }).text(name));
			$row.append($attachment);
			$row.append($('<td>').append($('<input>', { type: 'text', class: 'moltex-screenshot-route', value: route })));
			$row.append($('<td>').append($('<input>', { type: 'text', class: 'moltex-screenshot-viewport', value: viewport })));
			$row.append($('<td>').append($('<input>', { type: 'text', class: 'moltex-screenshot-label', value: label })));
			const $actions = $('<td>');
			$actions.append($('<button>', { type: 'button', class: 'button-link moltex-replace-screenshot' }).text('Replace'));
			$actions.append(document.createTextNode(' '));
			$actions.append($('<button>', { type: 'button', class: 'button-link-delete moltex-remove-screenshot' }).text('Remove'));
			$row.append($actions);
			$screenshotTable.append($row);
		}

		/**
		 * Handle export button click.
		 */
		$migrateBtn.on('click', function() {
			showBusyState();

			$.ajax({
				url: moltexExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'moltex_start_scan',
					nonce: moltexExporter.nonce
				},
				success: function(response) {
					if (!response.success) {
						showError(getResponseMessage(response, 'An error occurred.'));
						return;
					}

					showSuccess(response.data || {});
				},
				error: function(xhr, status, error) {
					showError(buildAjaxErrorMessage(xhr, error));
				}
			});
		});

		/**
		 * Handle download button click
		 */
		$downloadBtn.on('click', function() {
			// Get download URL from button data
			const downloadUrl = $downloadBtn.data('download-url');
			
			if (downloadUrl) {
				// Redirect to download URL
				window.location.href = downloadUrl;
			} else {
				showError('Download URL not available. Please try running the migration again.');
			}
		});

		/**
		 * Show the synchronous export busy state.
		 */
		function showBusyState() {
			$migrateBtn.prop('disabled', true);
			$successContainer.hide();
			$errorContainer.hide();
			$warningContainer.hide();
			$progressContainer.show();
			$progressFill.addClass('is-busy').css('width', '100%');
			$progressStage.text('Export running');
			$progressText.text('This export runs in a single request. Keep this page open until the server responds.');
		}

		/**
		 * Show the final success state.
		 */
		function showSuccess(data) {
			$progressFill.removeClass('is-busy').css('width', '100%');
			$progressStage.text('Export complete');
			$progressText.text(data.message || 'Export completed successfully.');

			if (data.download_url) {
				$downloadBtn.data('download-url', data.download_url);
			}

			if (data.has_issues && (data.warnings || data.errors)) {
				showWarnings(data.warnings, data.errors);
			}

			setTimeout(function() {
				$progressContainer.hide();
				$successContainer.show();
				$migrateBtn.prop('disabled', false);
			}, 300);
		}

		/**
		 * Show an error message.
		 */
		function showError(message) {
			$migrateBtn.prop('disabled', false);
			$progressFill.removeClass('is-busy').css('width', '0%');
			$progressStage.text('');
			$progressText.text('');
			$progressContainer.hide();
			$successContainer.hide();
			$warningContainer.hide();
			$errorMessage.html('<strong>Error:</strong> ' + escapeHtml(message));
			$errorContainer.show();
		}

		/**
		 * Show warnings and non-critical errors.
		 */
		function showWarnings(warnings, errors) {
			let message = '<strong>Note:</strong> The export completed with some issues:<br><br>';
			
			if (errors && errors.length > 0) {
				message += '<strong>Non-critical errors (' + errors.length + '):</strong><br>';
				message += '<ul style="margin: 5px 0 10px 20px;">';
				errors.slice(0, 3).forEach(function(error) {
					message += '<li>' + escapeHtml(error.message || error) + '</li>';
				});
				if (errors.length > 3) {
					message += '<li><em>... and ' + (errors.length - 3) + ' more</em></li>';
				}
				message += '</ul>';
			}
			
			if (warnings && warnings.length > 0) {
				message += '<strong>Warnings (' + warnings.length + '):</strong><br>';
				message += '<ul style="margin: 5px 0 10px 20px;">';
				warnings.slice(0, 3).forEach(function(warning) {
					message += '<li>' + escapeHtml(warning.message || warning) + '</li>';
				});
				if (warnings.length > 3) {
					message += '<li><em>... and ' + (warnings.length - 3) + ' more</em></li>';
				}
				message += '</ul>';
			}
			
			message += '<br><em>Full details are available in error_log.json within the downloaded ZIP file.</em>';
			
			$warningMessage.html(message);
			$warningContainer.show();
		}

		/**
		 * Build a human-readable AJAX error message.
		 */
		function buildAjaxErrorMessage(xhr, error) {
			let errorMsg = 'AJAX error: ' + error;

			if (xhr.status === 500) {
				errorMsg = 'Server error (500): The exporter request failed on the server. ';
				errorMsg += 'This is often a PHP fatal error or a request timeout. ';
				errorMsg += 'Check wp-content/debug.log and your PHP/server error logs for details. ';

				if (xhr.responseText) {
					const match = xhr.responseText.match(/Fatal error:([^<]+)/i);
					if (match) {
						errorMsg += 'Error: ' + match[1].trim();
					}
				}
			} else if (xhr.status === 0) {
				errorMsg = 'Network error: Could not connect to the server.';
			} else if (xhr.status === 403) {
				errorMsg = 'Permission denied (403): You do not have permission to perform this action.';
			} else if (xhr.status === 404) {
				errorMsg = 'Not found (404): The AJAX endpoint was not found. Please ensure the plugin is activated.';
			} else {
				errorMsg = 'HTTP ' + xhr.status + ' error: ' + error;
			}

			return errorMsg;
		}

		/**
		 * Extract a message from a WordPress AJAX response.
		 */
		function getResponseMessage(response, fallback) {
			return response && response.data && response.data.message
				? response.data.message
				: fallback;
		}

		/**
		 * Escape HTML to prevent XSS.
		 */
		function escapeHtml(text) {
			const map = {
				'&': '&amp;',
				'<': '&lt;',
				'>': '&gt;',
				'"': '&quot;',
				"'": '&#039;'
			};
			return String(text).replace(/[&<>"']/g, function(m) { return map[m]; });
		}
	});

})(jQuery);
