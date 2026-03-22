# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from memby.memby.doctype.bank_transaction.bank_transaction import link_to_bank_transaction, unlink_from_bank_transaction

class MembershipIncome(Document):
	def on_update(self):
		# Link to Bank Transaction if exists (on save)
		link_to_bank_transaction(self, "on_update")

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
		
		bank_doc = frappe.get_doc('Bank Account Balance', self.bank)
		bank_doc.remaining_balance -= self.amount
		bank_doc.save()

		# Unlink from Bank Transaction if linked
		unlink_from_bank_transaction(self, "on_cancel")
