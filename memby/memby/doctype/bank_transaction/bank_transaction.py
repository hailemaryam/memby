# Copyright (c) 2026, hailemaryam and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import re

class BankTransaction(Document):
	def validate(self):
		if self.message:
			self.parse_message()

	def on_update(self):
		# Auto-create Membership Income if conditions are met
		if self.type == "Credit" and self.sender_name and self.bank_account_number and not self.reference_name:
			self.auto_link_membership_income()

	def parse_message(self):
		message = self.message
		
		# Parsing logic
		holder_match = re.search(r"Dear ([^,]+),", message)
		if holder_match:
			self.bank_account_holder = holder_match.group(1).strip()
			
		account_match = re.search(r"your account ([\d\*]+) was", message)
		if account_match:
			self.bank_account_number = account_match.group(1).strip()
			
		type_match = re.search(r"was (credit|debit)ed with", message)
		if type_match:
			self.type = type_match.group(1).capitalize()
			
		amount_match = re.search(r"ETB ([\d,]+\.\d{2})", message)
		if amount_match:
			# Remove commas for float conversion
			amount_str = amount_match.group(1).replace(",", "")
			self.amount = float(amount_str)
			
		if self.type == "Credit":
			# "by Meseret Tibebu Gebremichael. Available Balance"
			sender_match = re.search(r"by ([^.]+)\. Available Balance", message)
			if sender_match:
				self.sender_name = sender_match.group(1).strip()
		else:
			self.sender_name = ""
			
		trx_match = re.search(r"trx=([^&\s?]+)", message)
		if trx_match:
			self.transaction_id = trx_match.group(1).strip()
			
		if not self.date:
			self.date = frappe.utils.today()

	def auto_link_membership_income(self):
		# 1. Search for Member by full_name
		member_name = frappe.db.get_value("Member", {"full_name": self.sender_name}, "name")
		
		# 2. Search for Bank Account Balance by account_number
		# We search for a record that HAS this account number
		bank_account = frappe.db.get_value("Bank Account Balance", {"account_number": self.bank_account_number}, "name")
		
		if member_name and bank_account:
			# 3. Check if Membership Income with this transaction_id already exists for this bank
			if not frappe.db.exists("Membership Income", {"transaction_id": self.transaction_id, "bank": bank_account}):
				try:
					# Create Membership Income
					mi_doc = frappe.get_doc({
						"doctype": "Membership Income",
						"member": member_name,
						"bank": bank_account,
						"amount": self.amount,
						"transaction_id": self.transaction_id,
						"time": frappe.utils.now_datetime()
					})
					mi_doc.insert(ignore_permissions=True)
					mi_doc.submit()
					
					# Link back to this transaction
					self.db_set("reference_doctype", "Membership Income")
					self.db_set("reference_name", mi_doc.name)
					
					frappe.msgprint(f"Automatically created and submitted Membership Income: {mi_doc.name}")
				except Exception:
					frappe.log_error(title="Auto-creation of Membership Income Failed", message=frappe.get_traceback())
