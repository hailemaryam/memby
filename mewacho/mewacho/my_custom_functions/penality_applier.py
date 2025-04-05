import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, add_days, today

@frappe.whitelist()
def apply_penalties():
    # Get Mewacho Setting
    setting = frappe.get_single("Mewacho Setting")

    payment_terms = frappe.db.sql("""
        SELECT name, start_date, end_date, amount, is_paid, penalized
        FROM `tabMewacho Payment Term`
        WHERE (is_paid = 0 AND penalized = 0)
    """, as_dict=True)

    for term in payment_terms:
        payment_term = frappe.get_doc("Mewacho Payment Term", term.name);
        if getdate() > payment_term.end_date:
            overdue_days = (getdate() - payment_term.end_date).days
            if overdue_days >= setting.no_of_days_before_penality:
                # Calculate the penalty
                penalty_value = CalculatePenality(payment_term, setting)
                # Insert penalty entry in Penality table
                penalty_doc = frappe.new_doc("Mewacho Penality")
                penalty_doc.parent = payment_term.parent  # Member name
                penalty_doc.parenttype = 'Mewacho Member'  # Parent DocType
                penalty_doc.parentfield = 'penality_list'  # Child table field in Mewacho Member
                penalty_doc.reason = "Penalty for overdue payment term from {} to {}".format(
                    str(payment_term.start_date) if payment_term.start_date else "N/A", 
                    str(payment_term.end_date) if payment_term.end_date else "N/A"
                )
                penalty_doc.amount = penalty_value
                penalty_doc.status = "Unpaid"
                penalty_doc.created_date = getdate()
                penalty_doc.insert(ignore_permissions=True)
                # Optionally, mark the payment term as penalized (or add comments, etc.)
                payment_term.penalized = 1
                payment_term.save()

    frappe.db.commit()

def CalculatePenality(payment_term, setting):
    # Calculate the penalty
    penalty_value = 0
    if setting.penality_based_on == "Percent":
        # Apply penalty percent to the amount
        penalty_value = (payment_term.amount * setting.penality_percent) / 100
    elif setting.penality_based_on == "Fixed Amount":
        # Use the fixed penalty amount
        penalty_value = setting.penality_amount
    return penalty_value

