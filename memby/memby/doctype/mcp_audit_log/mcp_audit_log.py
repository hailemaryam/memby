# Copyright (c) 2026, hailemaryammecca@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, nowdate


class MCPAuditLog(Document):
	@staticmethod
	def clear_old_logs(days=180):
		"""Called by Frappe's Log Settings cleanup job."""
		frappe.db.delete("MCP Audit Log", {"creation": ("<", add_days(nowdate(), -days))})
