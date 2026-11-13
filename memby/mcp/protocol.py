"""Minimal, framework-free MCP (Model Context Protocol) JSON-RPC dispatcher.

Implements the stateless subset of the Streamable HTTP transport that a
read-only tool server needs: ``initialize``, ``ping``, ``tools/list`` and
``tools/call``. Responses are plain JSON (no SSE stream), which the spec allows.

Kept free of Frappe imports so it can be unit-tested without a bench.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
	"""Raised by a tool for an expected, user-facing failure (bad input, not found, no permission).

	It is returned to the model as a tool result with ``isError: true`` so the
	model can read it and recover, rather than as a protocol error.
	"""


@dataclass
class Tool:
	name: str
	description: str
	input_schema: dict
	handler: Callable[..., Any]
	title: str | None = None
	annotations: dict = field(default_factory=lambda: {"readOnlyHint": True, "openWorldHint": False})

	def describe(self) -> dict:
		out = {"name": self.name, "description": self.description, "inputSchema": self.input_schema}
		if self.title:
			out["title"] = self.title
			out["annotations"] = {"title": self.title, **self.annotations}
		else:
			out["annotations"] = dict(self.annotations)
		return out


@dataclass
class ServerInfo:
	name: str
	version: str
	instructions: str = ""


def _error(msg_id, code: int, message: str) -> dict:
	return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id, result: dict) -> dict:
	return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def parse_body(raw: bytes | str) -> tuple[Any, dict | None]:
	"""Return (message, error_response). Exactly one of them is meaningful."""
	try:
		return json.loads(raw or b""), None
	except (ValueError, TypeError):
		return None, _error(None, PARSE_ERROR, "Parse error: body is not valid JSON")


def dispatch(
	message: Any,
	tools: dict[str, Tool],
	info: ServerInfo,
	on_tool_call: Callable[[str, dict, Callable[[], Any]], Any] | None = None,
) -> dict | None:
	"""Handle one JSON-RPC message. Returns the response dict, or None for notifications/responses.

	``on_tool_call(name, arguments, run)`` lets the caller wrap execution (audit logging,
	timing); it must call ``run()`` and return its value or let its exception propagate.
	"""
	if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
		return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Invalid Request")

	method = message.get("method")
	msg_id = message.get("id")
	is_notification = "id" not in message

	if method is None:
		# A JSON-RPC response sent by the client (we never send requests) - nothing to do.
		return None
	if is_notification:
		# notifications/initialized, notifications/cancelled, ... : acknowledge silently.
		return None

	params = message.get("params") or {}
	if not isinstance(params, dict):
		return _error(msg_id, INVALID_PARAMS, "params must be an object")

	if method == "initialize":
		requested = params.get("protocolVersion")
		version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
		result = {
			"protocolVersion": version,
			"capabilities": {"tools": {"listChanged": False}},
			"serverInfo": {"name": info.name, "version": info.version},
		}
		if info.instructions:
			result["instructions"] = info.instructions
		return _result(msg_id, result)

	if method == "ping":
		return _result(msg_id, {})

	if method == "tools/list":
		return _result(msg_id, {"tools": [t.describe() for t in tools.values()]})

	if method == "tools/call":
		name = params.get("name")
		arguments = params.get("arguments") or {}
		tool = tools.get(name)
		if tool is None:
			return _error(msg_id, INVALID_PARAMS, f"Unknown tool: {name}")
		if not isinstance(arguments, dict):
			return _error(msg_id, INVALID_PARAMS, "arguments must be an object")
		return _result(msg_id, _call_tool(tool, arguments, on_tool_call))

	return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def _call_tool(tool: Tool, arguments: dict, on_tool_call) -> dict:
	try:
		inspect.signature(tool.handler).bind(**arguments)
	except TypeError as e:
		return {"content": [{"type": "text", "text": f"Invalid arguments: {e}"}], "isError": True}

	def run():
		return tool.handler(**arguments)

	try:
		data = on_tool_call(tool.name, arguments, run) if on_tool_call else run()
	except ToolError as e:
		return {"content": [{"type": "text", "text": str(e)}], "isError": True}

	text = json.dumps(data, default=str, ensure_ascii=False, indent=1)
	result = {"content": [{"type": "text", "text": text}]}
	if isinstance(data, dict):
		result["structuredContent"] = json.loads(text)
	return result
