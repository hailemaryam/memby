import frappe

from memby.mcp.server import AI_ROLE


def after_migrate():
	ensure_ai_role()


def ensure_ai_role():
	if frappe.db.exists("Role", AI_ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": AI_ROLE,
			"desk_access": 0,
			"description": "Allows the user to connect AI tools (Claude etc.) to Memby through the read-only MCP connector. "
			"Data access still follows the user's other roles.",
		}
	).insert(ignore_permissions=True)
