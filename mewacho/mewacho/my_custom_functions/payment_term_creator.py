import frappe
from frappe.utils import getdate, add_days, today

def create_payment_terms_for_members():
    for member in getMembers():
        member_doc = frappe.get_doc('Mewacho Member', member.name)
        create_payment_terms(member_doc)

def create_payment_terms(member):
    start_date = member.last_created_end_date or member.registration_date
    while start_date < getdate():
        end_date = add_days(start_date, 30)
        is_paid = member.remaining_total >= member.membership_fee
        payment_term = frappe.get_doc({
            'doctype': 'Mewacho Payment Term',
            'parent': member.name,
            'parenttype': 'Mewacho Member',
            'parentfield': 'payment_terms',
            'amount': member.membership_fee,
            'is_paid': is_paid,
            'penalized': False,
            'start_date': start_date,
            'end_date': end_date
        })
        if is_paid:
            member.remaining_total -= member.membership_fee
        else:
            member.unpaid_total += member.membership_fee
        member.append('payment_terms', payment_term)
        start_date = end_date
    member.last_created_end_date = start_date
    member.save()

def getMembers():
    return frappe.db.sql("""
        SELECT name, registration_date, membership_fee, last_created_end_date
        FROM `tabMewacho Member`
        WHERE (last_created_end_date <= %s OR last_created_end_date IS NULL)
    """, (today(),), as_dict=True)


