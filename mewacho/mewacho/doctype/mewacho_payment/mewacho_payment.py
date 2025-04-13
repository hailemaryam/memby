# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MewachoPayment(Document):
	def after_insert(self):
		if not self.amount or not self.member:
			frappe.throw("Amount and Member are required.")

		amount = self.amount
		member_doc = frappe.get_doc('Mewacho Member', self.member)
		member_doc.total_payment_received += amount

		penalityAllocated = 0
		paymentTermAllocated = 0
		for payment_term in member_doc.payment_terms:
			if not payment_term.is_paid and amount >= payment_term.amount:
				payment_term.db_set('is_paid', True)
				amount -= payment_term.amount
				paymentTermAllocated += payment_term.amount

		for penality in member_doc.penality_list:
			if penality.status == 'Unpaid' and amount >= penality.amount:
				penality.db_set('status', 'Paid')
				amount-= penality.amount
				penalityAllocated += penality.amount

		member_doc.remaining_total += amount
		member_doc.save()
		printMessage(paymentTermAllocated, penalityAllocated, member_doc.remaining_total)

	def printMessage(paymentTermAllocated, penalityAllocated, remaining_total):
		frappe.msgprint(
			"This is allocation of this payment \n"
			+ "{} allocated for Payment Term \n"
			+ "{} allocated for Penality \n"
			+ "remaining amount is {}.".
			format(paymentTermAllocated, penalityAllocated, remaining_total))

