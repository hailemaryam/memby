# Copyright (c) 2025, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MewachoMember(Document):
	def before_insert(self):
		if not self.registration_date:
			self.registration_date = frappe.utils.today()
