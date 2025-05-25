# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class MewachoExpense(Document):
	
	def on_submit(self):
		bank_doc = frappe.get_doc('Mewacho Bank', self.bank_account)
		bank_doc.remaining_balance -= self.amount
		bank_doc.save()

    def on_cancel(self):
        bank_doc = frappe.get_doc('Mewacho Bank', self.bank_account)
        bank_doc.remaining_balance += self.amount
        bank_doc.save()
