// Copyright (c) 2026, hailemaryam and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bank Transaction', {
	refresh: function(frm) {
		frm.set_query('reference_doctype', function() {
			let allowed_doctypes = ['Internal Transfer'];
			if (frm.doc.type === 'Credit') {
				allowed_doctypes.push('Membership Income', 'Other Income');
			} else if (frm.doc.type === 'Debit') {
				allowed_doctypes.push('Expense');
			}
			return {
				filters: {
					'name': ['in', allowed_doctypes]
				}
			};
		});

		if (!frm.doc.reference_name && frm.doc.transaction_id && frm.doc.docstatus === 0) {
			if (frm.doc.type === 'Credit') {
				frm.add_custom_button(__('Membership Income'), () => {
					create_linked_doc(frm, 'Membership Income');
				}, __('Create Linked Record'));
				
				frm.add_custom_button(__('Other Income'), () => {
					create_linked_doc(frm, 'Other Income');
				}, __('Create Linked Record'));
			} else if (frm.doc.type === 'Debit') {
				frm.add_custom_button(__('Expense'), () => {
					create_linked_doc(frm, 'Expense');
				}, __('Create Linked Record'));
			}

			frm.add_custom_button(__('Internal Transfer'), () => {
				create_linked_doc(frm, 'Internal Transfer');
			}, __('Create Linked Record'));
		}
	},
	message: function(frm) {
		if (frm.doc.message) {
			// Trigger server-side parsing
			frm.save();
		}
	}
});

function create_linked_doc(frm, doctype) {
	frappe.db.get_value('Bank Account Balance', {'account_number': frm.doc.bank_account_number}, 'name', (r) => {
		let bank = (r && r.name) ? r.name : null;
		let route_params = {
			'amount': frm.doc.amount,
			'transaction_id': frm.doc.transaction_id,
		};
		
		// Handle date/time fields based on doctype requirements
		if (doctype === 'Membership Income' || doctype === 'Internal Transfer') {
			route_params['time'] = frm.doc.date ? (frm.doc.date + " 00:00:00") : frappe.datetime.now_datetime();
		} else {
			route_params['date'] = frm.doc.date || frappe.datetime.get_today();
		}

		if (doctype === 'Internal Transfer') {
			if (frm.doc.type === 'Debit') {
				route_params['from_bank_account'] = bank;
			} else {
				route_params['to_bank_account'] = bank;
			}
		} else if (doctype === 'Membership Income') {
			route_params['bank'] = bank;
		} else {
			// Other Income and Expense use bank_account
			route_params['bank_account'] = bank;
		}

		frappe.new_doc(doctype, route_params);
	});
}
