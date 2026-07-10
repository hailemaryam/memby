// Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('Memby Setting', {
	refresh: function(frm) {
		toggle_penality_fields(frm);
		toggle_sms_fields(frm);
		setup_sms_buttons(frm);
	},

	penality_based_on: function(frm) {
		toggle_penality_fields(frm);
	},

	enable_sms_notifications: function(frm) {
		toggle_sms_fields(frm);
		setup_sms_buttons(frm);
	}
});

function toggle_penality_fields(frm) {
	if (frm.doc.penality_based_on === 'Percent') {
		frm.set_df_property('penality_percent', 'hidden', 0);
		frm.set_df_property('penality_amount', 'hidden', 1);
	} else if (frm.doc.penality_based_on === 'Fixed Amount') {
		frm.set_df_property('penality_percent', 'hidden', 1);
		frm.set_df_property('penality_amount', 'hidden', 0);
	}
	frm.refresh_fields();
}

function toggle_sms_fields(frm) {
	const enabled = !!frm.doc.enable_sms_notifications;
	['sms_gateway_user', 'sms_gateway_password', 'sms_payment_reminder_message'].forEach(
		function(fieldname) {
			frm.set_df_property(fieldname, 'hidden', enabled ? 0 : 1);
		}
	);
	frm.refresh_fields();
}

function setup_sms_buttons(frm) {
	frm.remove_custom_button(__('Send Custom SMS'));
	frm.remove_custom_button(__('Send Payment Reminder'));

	if (!frm.doc.enable_sms_notifications) {
		return;
	}

	frm.add_custom_button(__('Send Payment Reminder'), function() {
		frappe.confirm(
			__(
				'Send the configured payment reminder to all Active members with an unpaid balance?'
			),
			function() {
				frappe.call({
					method:
						'memby.memby.my_custom_functions.payment_sms_notifier.send_payment_reminders',
					args: { manual: 1 },
					freeze: true,
					freeze_message: __('Sending payment reminders...'),
					callback: function(r) {
						if (!r.message) {
							return;
						}
						frappe.msgprint({
							title: __('Payment Reminder SMS'),
							indicator: r.message.failed ? 'orange' : 'green',
							message: __(
								'Sent: {0}, Failed: {1}, Total members: {2}',
								[r.message.sent, r.message.failed, r.message.total]
							)
						});
					}
				});
			}
		);
	});

	frm.add_custom_button(__('Send Custom SMS'), function() {
		frappe.prompt(
			[
				{
					fieldname: 'message',
					fieldtype: 'Small Text',
					label: __('Message'),
					reqd: 1,
					description: __(
						'Placeholders: {full_name}, {unpaid_total}, {company_name}, {phone}'
					)
				}
			],
			function(values) {
				frappe.confirm(
					__(
						'Send this message to all Active members? This cannot be undone.'
					),
					function() {
						frappe.call({
							method:
								'memby.memby.my_custom_functions.payment_sms_notifier.send_custom_message',
							args: { message: values.message },
							freeze: true,
							freeze_message: __('Sending SMS to Active members...'),
							callback: function(r) {
								if (!r.message) {
									return;
								}
								frappe.msgprint({
									title: __('Custom SMS'),
									indicator: r.message.failed ? 'orange' : 'green',
									message: __(
										'Sent: {0}, Failed: {1}, Total members: {2}',
										[
											r.message.sent,
											r.message.failed,
											r.message.total
										]
									)
								});
							}
						});
					}
				);
			},
			__('Send Custom SMS'),
			__('Send')
		);
	});
}
