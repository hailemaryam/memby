# Copyright (c) 2026, hailemaryam and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from memby.memby.doctype.bank_transaction.bank_transaction import link_to_bank_transaction, unlink_from_bank_transaction

class InternalTransfer(Document):
	def validate(self):
		if self.from_bank_account == self.to_bank_account:
			frappe.throw("From Bank Account and To Bank Account must be different.")
		
		if self.amount <= 0:
			frappe.throw("Amount must be greater than zero.")

	def on_submit(self):
		# Decrease balance of from_bank_account
		from_bank = frappe.get_doc("Bank Account Balance", self.from_bank_account)
		from_bank.remaining_balance -= self.amount
		from_bank.save()

		# Increase balance of to_bank_account
		to_bank = frappe.get_doc("Bank Account Balance", self.to_bank_account)
		to_bank.remaining_balance += self.amount
		to_bank.save()

		# Link to Bank Transaction if exists
		link_to_bank_transaction(self, "on_submit")

	def on_cancel(self):
		# Revert decrease balance of from_bank_account
		from_bank = frappe.get_doc("Bank Account Balance", self.from_bank_account)
		from_bank.remaining_balance += self.amount
		from_bank.save()

		# Revert increase balance of to_bank_account
		to_bank = frappe.get_doc("Bank Account Balance", self.to_bank_account)
		to_bank.remaining_balance -= self.amount
		to_bank.save()

		# Unlink from Bank Transaction if linked
		unlink_from_bank_transaction(self, "on_cancel")
