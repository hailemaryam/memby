import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, add_days, today

@frappe.whitelist() 
def apply_penalties():
    # Get Memby Setting
    setting = frappe.get_single("Memby Setting")
    last_penality_date = datetime.now() - timedelta(days=setting.no_of_days_before_penality)
    for term in getUnPaidUnPenalizedTerms(last_penality_date):
        payment_term = frappe.get_doc("Monthly Payment", term.name)
        member_doc = frappe.get_doc('Member', payment_term.parent)
        penalty_value = CalculatePenality(payment_term, setting)
        savePenality(member_doc, payment_term, penalty_value)
        payment_term = frappe.get_doc("Monthly Payment", term.name)
        payment_term.penalized = 1
        payment_term.save()

def savePenality(member_doc, payment_term, penalty_value):
    penalty_doc = frappe.new_doc("Other Payment")
    penalty_doc.parent = payment_term.parent  # Member name
    penalty_doc.parenttype = 'Member'  # Parent DocType
    penalty_doc.parentfield = 'other_payments'  # Child table field in Memby Member
    penalty_doc.reason = "Penalty for overdue payment term from {} to {}".format(
        str(payment_term.start_date) if payment_term.start_date else "N/A", 
        str(payment_term.end_date) if payment_term.end_date else "N/A"
    )
    penalty_doc.amount = penalty_value
    penalty_doc.status = "Unpaid"
    penalty_doc.created_date = getdate()
    member_doc.append('other_payments', penalty_doc)
    member_doc.save()

def getUnPaidUnPenalizedTerms(last_penality_date):
    return frappe.db.sql("""
        SELECT name, start_date, end_date, amount, is_paid, penalized
        FROM `tabMonthly Payment`
        WHERE (is_paid = 0 AND penalized = 0) AND end_date <= %s
    """, (last_penality_date,), as_dict=True)

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

