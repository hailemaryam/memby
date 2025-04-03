import frappe
from datetime import timedelta
from frappe.utils import getdate

def create_payment_terms_for_members():
    members = frappe.get_all('Mewacho Member', filters={'registration_date': ['is', 'set']})    
    for member in members:
        member_doc = frappe.get_doc('Mewacho Member', member.name)
        existing_terms = frappe.get_all('Mewacho Payment Term', filters={'parent': member.name}, order_by='end_date desc')
        if not existing_terms:
            if member_doc.registration_date.date() > getdate():
                frappe.log_error(f"Skipping Payment Term creation for Member: {member.name} due to future registration date.", "Payment Term Creation")
                continue  # Skip payment term creation for this member                
            create_payment_terms(member_doc, member_doc.registration_date)
        else:
            last_end_date = existing_terms[0].get('end_date')
            if last_end_date and (getdate() - last_end_date.date()).days > 30:
                create_payment_terms(member_doc, last_end_date)

def create_payment_terms(member, start_date):
    if not start_date:
        start_date = member.registration_date    
    while start_date.date() < getdate():
        end_date = start_date + timedelta(days=30)
        payment_term = frappe.get_doc({
            'doctype': 'Mewacho Payment Term',
            'parent': member.name,
            'parenttype': 'Mewacho Member',
            'parentfield': 'payment_terms',
            'amount': member.memeber_ship_fee,
            'is_paid': False,
            'start_date': start_date,
            'end_date': end_date
        })
        payment_term.insert(ignore_permissions=True)
        frappe.db.commit()
        start_date = end_date
