# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MewachoMember(Document):
    def validate(self):
        calculate_remaining_and_unpaid_total(self)
        mark_unpaid_payments(self)

def calculate_remaining_and_unpaid_total(member):
    paid_total = 0
    unpaid_total = 0

    for payment in member.monthly_payments or []:
        if payment.is_paid:
            paid_total += payment.amount
        else:
            unpaid_total += payment.amount

    for other_payment in member.other_payments or []:
        if other_payment.status == "Paid":
            paid_total += other_payment.amount
        elif other_payment.status == "Unpaid":
            unpaid_total += other_payment.amount

    remaining_total = (member.total_payment_received or 0) - paid_total
    member.unpaid_total = unpaid_total
    member.remaining_total = remaining_total


def mark_unpaid_payments(member):
    if member.remaining_total > 0:
        for payment in member.monthly_payments or []:
            if not payment.is_paid and member.remaining_total >= payment.amount:
                payment.is_paid = True
                member.remaining_total -= payment.amount
                member.unpaid_total -= payment.amount

        for other_payment in member.other_payments or []:
            if other_payment.status == "Unpaid" and member.remaining_total >= other_payment.amount:
                other_payment.status = "Paid"
                member.remaining_total -= other_payment.amount
                member.unpaid_total -= other_payment.amount