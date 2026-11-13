"""MCP endpoint for Memby (read-only).

URL:  https://<site>/api/method/memby.mcp.server.handle

Authentication is Frappe's own: an OAuth2 bearer token (Frappe OAuth provider) or
``Authorization: token <api_key>:<api_secret>``. Every tool runs as the
authenticated user, so normal Frappe role permissions apply. On top of that the
user must have the ``AI Reader`` role (or be System Manager / Administrator):
it is the switch that says "this person may use AI connectors".
"""

import json
import time

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

from memby.mcp.protocol import ServerInfo, ToolError, dispatch, parse_body
from memby.mcp.tools import TOOLS

AI_ROLE = "AI Reader"
ALLOWED_ROLES = {AI_ROLE, "System Manager"}
MAX_LOGGED_ARGS = 2000

SERVER_INFO = ServerInfo(
	name="memby",
	version="1.0.0",
	instructions=(
		"Read-only access to the Memby membership & finance system. "
		"Amounts are in the organisation's currency (ETB unless stated). "
		"Dates are Gregorian ISO dates; fields ending in _ethiopian give the same date in the "
		"Ethiopian calendar - show those to the user when they talk in Ethiopian dates. "
		"Totals are computed by the server; prefer them over adding up rows yourself."
	),
)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST", "DELETE"])
@rate_limit(limit=120, seconds=60)
def handle(**kwargs):
	request = frappe.request

	if frappe.session.user == "Guest":
		return _unauthorized()

	if not _user_allowed():
		return _json({"error": f"User needs the '{AI_ROLE}' role to use the Memby MCP connector."}, 403)

	if request.method != "POST":
		# Stateless server: no SSE stream (GET) and no sessions to terminate (DELETE).
		return Response(status=405, headers={"Allow": "POST"})

	message, error = parse_body(request.get_data())
	if error:
		return _json(error, 400)

	response = dispatch(message, TOOLS, SERVER_INFO, on_tool_call=_audited_call)
	if response is None:
		return Response(status=202)
	return _json(response)


def _user_allowed() -> bool:
	if frappe.session.user == "Administrator":
		return True
	return bool(ALLOWED_ROLES.intersection(frappe.get_roles()))


def _unauthorized():
	resource_metadata = frappe.utils.get_url("/.well-known/oauth-protected-resource")
	return Response(
		json.dumps({"error": "Authentication required"}),
		status=401,
		content_type="application/json",
		headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata}"'},
	)


def _json(payload, status=200):
	return Response(json.dumps(payload, default=str), status=status, content_type="application/json")


def _audited_call(tool_name, arguments, run):
	started = time.monotonic()
	status, error_text, result = "Success", None, None
	try:
		result = run()
		return result
	except ToolError as e:
		status, error_text = "Error", str(e)
		raise
	except frappe.PermissionError:
		status, error_text = "Denied", "Permission denied"
		raise ToolError("You do not have permission to read the data this tool needs.")
	except frappe.ValidationError as e:
		status, error_text = "Error", str(e)
		raise ToolError(frappe.utils.strip_html(str(e)) or "Invalid request")
	except Exception:
		status, error_text = "Error", frappe.get_traceback()
		frappe.log_error(title=f"Memby MCP tool failed: {tool_name}")
		raise ToolError("The tool failed with an internal error. It has been logged for the administrator.")
	finally:
		_write_audit(tool_name, arguments, status, error_text, result, started)


def _write_audit(tool_name, arguments, status, error_text, result, started):
	try:
		args_text = json.dumps(arguments, default=str, ensure_ascii=False)
		frappe.get_doc(
			{
				"doctype": "MCP Audit Log",
				"user": frappe.session.user,
				"tool": tool_name,
				"arguments": args_text[:MAX_LOGGED_ARGS],
				"status": status,
				"error": (error_text or "")[:5000],
				"result_rows": _count_rows(result),
				"duration_ms": int((time.monotonic() - started) * 1000),
				"ip_address": frappe.local.request_ip,
			}
		).insert(ignore_permissions=True)
	except Exception:
		# Never let audit logging break the tool call itself.
		frappe.log_error(title="Memby MCP audit log write failed")


def _count_rows(result) -> int:
	if isinstance(result, dict):
		for value in result.values():
			if isinstance(value, list):
				return len(value)
		return 1
	if isinstance(result, list):
		return len(result)
	return 0
