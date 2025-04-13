import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, add_days, today

@frappe.whitelist()
def apply_penalties():
    # Get Mewacho Setting
    setting = frappe.get_single("Mewacho Setting")
    for term in getUnPaidUnPenalizedTerms():
        payment_term = frappe.get_doc("Mewacho Payment Term", term.name)
        if (getdate() - payment_term.end_date).days >= setting.no_of_days_before_penality:
            member_doc = frappe.get_doc('Mewacho Member', payment_term.parent)
            penalty_value = CalculatePenality(payment_term, setting)
            savePenalityAndMemeberDoc(member_doc, payment_term, penalty_value)
            payment_term = frappe.get_doc("Mewacho Payment Term", term.name)
            payment_term.penalized = 1
            payment_term.save()

def savePenalityAndMemeberDoc(member_doc, payment_term, penalty_value):
    penalty_doc = frappe.new_doc("Mewacho Penality")
    penalty_doc.parent = payment_term.parent  # Member name
    penalty_doc.parenttype = 'Mewacho Member'  # Parent DocType
    penalty_doc.parentfield = 'penality_list'  # Child table field in Mewacho Member
    penalty_doc.reason = "Penalty for overdue payment term from {} to {}".format(
        str(payment_term.start_date) if payment_term.start_date else "N/A", 
        str(payment_term.end_date) if payment_term.end_date else "N/A"
    )
    penalty_doc.amount = penalty_value
    penalty_doc.status = getPaymentStatusAndUpdatePaymentInfo(member_doc, penalty_value)
    penalty_doc.created_date = getdate()
    member_doc.append('penality_list', penalty_doc)
    member_doc.save()

def getPaymentStatusAndUpdatePaymentInfo(member_doc, penalty_value):
    paymentStatus = "Unpaid"
    if member_doc.remaining_total >= penalty_value:
        paymentStatus = 'Paid'
        member_doc.remaining_total -= penalty_value
    else:
        member_doc.unpaid_total += penalty_value
    return paymentStatus

def getUnPaidUnPenalizedTerms():
    return frappe.db.sql("""
        SELECT name, start_date, end_date, amount, is_paid, penalized
        FROM `tabMewacho Payment Term`
        WHERE (is_paid = 0 AND penalized = 0)
    """, as_dict=True)

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

