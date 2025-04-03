import frappe
from datetime import datetime, timedelta

@frappe.whitelist()
def apply_penalties():
    # Get Mewacho Setting
    setting = frappe.get_single("Mewacho Setting")
    no_of_days_before_penality = setting.no_of_days_before_penality
    penality_based_on = setting.penality_based_on
    penality_percent = setting.penality_percent
    penality_amount = setting.penality_amount

    # Get all Mewacho Members (You can filter based on other conditions if needed)
    members = frappe.get_all("Mewacho Member", fields=["name"])

    for member in members:
        # Get the full member document (including child table)
        member_doc = frappe.get_doc("Mewacho Member", member["name"])
        payment_terms = member_doc.payment_terms

        for payment_term in payment_terms:
            # Check if the payment term is eligible for penalty
            if payment_term.is_paid == 0 and payment_term.penalized == 0:  # Not paid and not penalized
                # Calculate the number of days past since 'to' date
                due_date = payment_term.end_date
                current_date = datetime.today().date()

                if current_date > due_date:
                    overdue_days = (current_date - due_date).days

                    if overdue_days >= no_of_days_before_penality:
                        # Calculate the penalty
                        penalty_value = 0

                        if penality_based_on == "Percent":
                            # Apply penalty percent to the amount
                            penalty_value = (payment_term.amount * penality_percent) / 100
                        elif penality_based_on == "Fixed Amount":
                            # Use the fixed penalty amount
                            penalty_value = penality_amount

                        # Insert penalty entry in Penality table
                        penalty_doc = frappe.new_doc("Mewacho Penality")
                        penalty_doc.parent = member_doc.name  # Member name
                        penalty_doc.parenttype = 'Mewacho Member'  # Parent DocType
                        penalty_doc.parentfield = 'penality_list'  # Child table field in Mewacho Member
                        penalty_doc.reason = "Penalty for overdue payment term from {} to {}".format(
                            str(payment_term.start_date) if payment_term.start_date else "N/A", 
                            str(payment_term.end_date) if payment_term.end_date else "N/A"
                        )
                        penalty_doc.amount = penalty_value
                        penalty_doc.status = "Unpaid"
                        penalty_doc.created_date = current_date

                        try:
                            penalty_doc.insert(ignore_permissions=True)
                        except Exception as e:
                            frappe.log_error(f"Error inserting penalty document: {e}")
                            raise

                        # Optionally, mark the payment term as penalized (or add comments, etc.)
                        payment_term.penalized = 1
                        payment_term.save()

    frappe.db.commit()
