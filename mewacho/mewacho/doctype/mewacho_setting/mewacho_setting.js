// Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Mewacho Setting", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on('Mewacho Setting', {
    // Trigger when the 'amount_type' field changes
    penality_based_on: function(frm) {
        if (frm.doc.penality_based_on === 'Percent') {
            frm.fields_dict['penality_percent'].df.hidden = false;
            frm.fields_dict['penality_amount'].df.hidden = true;
        } else if (frm.doc.penality_based_on === 'Fixed Amount') {
            frm.fields_dict['penality_percent'].df.hidden = true;
            frm.fields_dict['penality_amount'].df.hidden = false;
        }

        // Refresh the form to apply the changes
        frm.refresh_fields();
    }
});
