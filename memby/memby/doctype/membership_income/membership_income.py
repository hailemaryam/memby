# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MembershipIncome(Document): 
	def on_submit(self):
		if not self.amount or not self.member:
			frappe.throw("Amount and Member are required.")

		amount = self.amount
		member_doc = frappe.get_doc('Member', self.member)
		member_doc.total_payment_received += amount
		member_doc.save()
		
		bank_doc = frappe.get_doc('Bank Account Balance', self.bank)
		bank_doc.remaining_balance += self.amount
		bank_doc.save()

	def on_cancel(self):
		amount = self.amount
		member_doc = frappe.get_doc('Member', self.member)
		member_doc.total_payment_received -= amount
		member_doc.save()
		
		bank_doc = frappe.get_doc('', self.bank)
		bank_doc.remaining_balance -= self.amount
		bank_doc.save()
