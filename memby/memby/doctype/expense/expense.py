# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from memby.memby.doctype.bank_transaction.bank_transaction import link_to_bank_transaction, unlink_from_bank_transaction


class Expense(Document):
	
	def on_submit(self):
		bank_doc = frappe.get_doc('Bank Account Balance', self.bank_account)
		bank_doc.remaining_balance -= self.amount
		bank_doc.save()

		# Link to Bank Transaction if exists
		link_to_bank_transaction(self, "on_submit")

	def on_cancel(self):
		bank_doc = frappe.get_doc('Bank Account Balance', self.bank_account)
		bank_doc.remaining_balance += self.amount
		bank_doc.save()
		
		# Unlink from Bank Transaction if linked
		unlink_from_bank_transaction(self, "on_cancel")
