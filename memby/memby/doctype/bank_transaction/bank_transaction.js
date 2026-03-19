// Copyright (c) 2026, hailemaryam and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bank Transaction', {
	refresh: function(frm) {
		frm.set_query('reference_doctype', function() {
			return {
				filters: {
					'name': ['in', ['Membership Income', 'Other Income', 'Expense']]
				}
			};
		});
	},
	message: function(frm) {
		if (frm.doc.message) {
			// Trigger server-side parsing
			frm.save();
		}
	}
});
