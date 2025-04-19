# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MewachoPayment(Document): 
	def on_submit(self):
		if not self.amount or not self.member:
			frappe.throw("Amount and Member are required.")

		amount = self.amount
		member_doc = frappe.get_doc('Mewacho Member', self.member)
		member_doc.total_payment_received += amount

		penalityAllocated = 0
		paymentTermAllocated = 0
		for payment_term in member_doc.monthly_payments:
			if not payment_term.is_paid and amount >= payment_term.amount:
				payment_term.db_set('is_paid', True)
				amount -= payment_term.amount
				paymentTermAllocated += payment_term.amount
				member_doc.unpaid_total -= payment_term.amount

		for other_payment in member_doc.other_payments:
			if other_payment.status == 'Unpaid' and amount >= other_payment.amount:
				other_payment.db_set('status', 'Paid')
				amount-= other_payment.amount
				penalityAllocated += other_payment.amount
				member_doc.unpaid_total -= other_payment.amount

		member_doc.remaining_total += amount
		member_doc.save()
		bank_doc = frappe.get_doc('Mewacho Bank', self.bank)
		bank_doc.remaining_balance += self.amount
		bank_doc.save()
		message = "From this payment \n"
		message += "<br>"
		message += "{} allocated for Monthly Payment and \n".format(paymentTermAllocated)
		message += "<br>"
		message += "{} allocated for Other unpaid payments \n".format(penalityAllocated)
		frappe.msgprint(message)

