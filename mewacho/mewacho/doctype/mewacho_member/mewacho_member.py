# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MewachoMember(Document):
    def validate(self):
        paid_total = 0
        unpaid_total = 0

        for payment in self.monthly_payments:
            if payment.is_paid:
                paid_total += payment.amount
            else:
                unpaid_total += payment.amount

        for other_payment in self.other_payments:
            if other_payment.status == "Paid":
                paid_total += other_payment.amount
            elif other_payment.status == "Unpaid":
                unpaid_total += other_payment.amount

        remaining_total = self.total_payment_received - paid_total

        # Try to mark some unpaid payments as paid if funds allow
        if remaining_total > 0:
            for other_payment in self.other_payments:
                if other_payment.status == "Unpaid" and remaining_total >= other_payment.amount:
                    other_payment.status = "Paid"
                    remaining_total -= other_payment.amount
                    unpaid_total -= other_payment.amount

        self.unpaid_total = unpaid_total
        self.remaining_total = remaining_total
