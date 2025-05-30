frappe.ui.form.on('Expense Item', {
    unit_price: function(frm, cdt, cdn) {
        calculate_amount(frm, cdt, cdn);
    },
    quantity: function(frm, cdt, cdn) {
        calculate_amount(frm, cdt, cdn);
    }
});

function calculate_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (row.unit_price && row.quantity) {
        let amount = row.unit_price * row.quantity;
        frappe.model.set_value(cdt, cdn, 'amount', amount).then(() => {
            frm.fields_dict["item_list"].grid.refresh(); // 👈 force refresh UI
        });
    }
}

frappe.ui.form.on('Expense', {
    validate: function(frm) {
        let total = 0;
        (frm.doc.item_list || []).forEach(row => {
            total += row.amount || 0;
        });

        if (frm.doc.amount !== total) {
            frappe.throw(__('Total amount in Item List ({0}) must match the main Amount field ({1}).', [total, frm.doc.amount]));
        }
    }
});
