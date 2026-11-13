"""Read-only MCP tools over Memby data.

Rules every tool follows:
* Check the caller's Frappe read permission on each doctype before touching it
  (``frappe.get_list`` does this itself; raw SQL is always preceded by ``_require_read``).
* Return only the fields the question needs. Sensitive member fields (mother's name,
  date of birth, photo, emergency contacts, relatives) are never returned.
* Do the arithmetic here, so the model reports server-computed totals.
* Cap row counts.
"""

from datetime import date

import frappe
from frappe.utils import flt, get_first_day, getdate, nowdate

from memby.mcp.protocol import Tool, ToolError

MAX_LIMIT = 200
MEMBER_STATUSES = ["Active", "De active", "Removed"]
MEMBER_ID_DIGITS = 7  # Member autoname is format:{#######}


# --------------------------------------------------------------------------- helpers


def _require_read(*doctypes):
	for doctype in doctypes:
		if not frappe.has_permission(doctype, "read"):
			raise ToolError(f"You do not have permission to read {doctype} records.")


def _can_read(doctype) -> bool:
	return bool(frappe.has_permission(doctype, "read"))


def _limit(value, default) -> int:
	try:
		value = int(value if value is not None else default)
	except (TypeError, ValueError):
		raise ToolError("limit must be a whole number")
	return max(1, min(value, MAX_LIMIT))


def _money(value) -> float:
	return flt(value, 2)


def _date(value, name):
	if value in (None, ""):
		return None
	try:
		return getdate(value)
	except Exception:
		raise ToolError(f"{name} must be a date in YYYY-MM-DD format (got {value!r})")


def _range(from_date, to_date, default_from=None):
	start = _date(from_date, "from_date") or default_from
	end = _date(to_date, "to_date") or getdate(nowdate())
	if start and start > end:
		raise ToolError("from_date must be on or before to_date")
	return start, end


def _eth(value):
	"""Ethiopian-calendar rendering of a date, or None."""
	if not value:
		return None
	try:
		from memby.utils.abushahir_date import to_abushahir

		return to_abushahir(getdate(value))
	except Exception:
		return None


def _with_eth(row: dict, *fields) -> dict:
	for f in fields:
		if f in row:
			row[f"{f}_ethiopian"] = _eth(row[f])
	return row


def _period(start, end) -> dict:
	return {
		"from_date": str(start) if start else None,
		"to_date": str(end),
		"from_date_ethiopian": _eth(start),
		"to_date_ethiopian": _eth(end),
	}


def _resolve_member(member: str) -> str:
	"""Turn a member ID, phone number or name into exactly one Member name."""
	member = str(member if member is not None else "").strip()
	if not member:
		raise ToolError("member is required (member ID, phone number or full name)")
	_require_read("Member")

	candidates = [{"name": member}]
	if member.isdigit() and len(member) < MEMBER_ID_DIGITS:
		# Member IDs are zero-padded ("0000012"); accept "12".
		candidates.append({"name": member.zfill(MEMBER_ID_DIGITS)})
	candidates += [{"phone": member}, {"full_name": member}]
	for filters in candidates:
		found = frappe.get_list("Member", filters=filters, pluck="name", limit_page_length=2)
		if len(found) == 1:
			return found[0]
		if len(found) > 1:
			break

	matches = frappe.get_list(
		"Member",
		or_filters={"full_name": ["like", f"%{member}%"], "nick_name": ["like", f"%{member}%"]},
		fields=["name", "full_name", "phone", "status"],
		limit_page_length=10,
	)
	if len(matches) == 1:
		return matches[0].name
	if not matches:
		raise ToolError(f"No member found for {member!r}. Try search_members.")
	listed = "; ".join(f"{m.name} {m.full_name} ({m.status}, {m.phone or 'no phone'})" for m in matches)
	raise ToolError(f"{member!r} matches several members - ask which one, then pass the member ID: {listed}")


# --------------------------------------------------------------------------- tools


def search_members(query=None, status=None, limit=20):
	_require_read("Member")
	limit = _limit(limit, 20)
	filters = {}
	if status:
		if status not in MEMBER_STATUSES:
			raise ToolError(f"status must be one of {MEMBER_STATUSES}")
		filters["status"] = status
	or_filters = None
	if query:
		like = f"%{str(query).strip()}%"
		or_filters = {
			"name": ["like", like],
			"full_name": ["like", like],
			"nick_name": ["like", like],
			"phone": ["like", like],
		}
	rows = frappe.get_list(
		"Member",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "nick_name", "phone", "status", "membership_fee", "unpaid_total"],
		order_by="full_name asc",
		limit_page_length=limit + 1,
	)
	return {
		"members": rows[:limit],
		"truncated": len(rows) > limit,
	}


def get_member(member):
	name = _resolve_member(member)
	doc = frappe.get_doc("Member", name)
	doc.check_permission("read")

	unpaid_terms = [
		_with_eth(
			{
				"start_date": t.start_date,
				"end_date": t.end_date,
				"amount": flt(t.amount),
				"penalized": bool(t.penalized),
			},
			"start_date",
			"end_date",
		)
		for t in sorted(doc.monthly_payments or [], key=lambda t: t.start_date or date.min)
		if not t.is_paid
	]
	unpaid_other = [
		_with_eth({"reason": p.reason, "amount": flt(p.amount), "created_date": p.created_date}, "created_date")
		for p in doc.other_payments or []
		if p.status == "Unpaid"
	]

	return _with_eth(
		{
			"member_id": doc.name,
			"full_name": doc.full_name,
			"nick_name": doc.nick_name,
			"gender": doc.gender,
			"phone": doc.phone,
			"email": doc.email,
			"address": doc.address,
			"status": doc.status,
			"registration_date": doc.registration_date,
			"membership_fee": flt(doc.membership_fee),
			"total_payment_received": flt(doc.total_payment_received),
			"unpaid_total": flt(doc.unpaid_total),
			"credit_balance": flt(doc.remaining_total),
			"terms_created_until": doc.last_created_end_date,
			"monthly_terms_total": len(doc.monthly_payments or []),
			"monthly_terms_unpaid": len(unpaid_terms),
			"unpaid_terms": unpaid_terms,
			"unpaid_other_payments": unpaid_other,
		},
		"registration_date",
		"terms_created_until",
	)


def list_members_with_arrears(min_unpaid_terms=1, status="Active", overdue_only=True, limit=50):
	_require_read("Member")
	limit = _limit(limit, 50)
	try:
		min_unpaid_terms = max(1, int(min_unpaid_terms or 1))
	except (TypeError, ValueError):
		raise ToolError("min_unpaid_terms must be a whole number")
	if status not in (*MEMBER_STATUSES, "Any"):
		raise ToolError(f"status must be one of {[*MEMBER_STATUSES, 'Any']}")

	conditions = ["mp.is_paid = 0"]
	values = {"min_terms": min_unpaid_terms, "today": nowdate()}
	if overdue_only:
		conditions.append("mp.end_date <= %(today)s")
	member_condition = ""
	if status != "Any":
		member_condition = "AND m.status = %(status)s"
		values["status"] = status

	rows = frappe.db.sql(
		f"""
		SELECT m.name AS member_id, m.full_name, m.phone, m.status,
			COUNT(mp.name) AS unpaid_terms,
			SUM(mp.amount) AS unpaid_terms_amount,
			MIN(mp.start_date) AS oldest_unpaid_from,
			m.unpaid_total
		FROM `tabMember` m
		JOIN `tabMonthly Payment` mp
			ON mp.parent = m.name AND mp.parenttype = 'Member' AND {" AND ".join(conditions)}
		WHERE 1=1 {member_condition}
		GROUP BY m.name, m.full_name, m.phone, m.status, m.unpaid_total
		HAVING COUNT(mp.name) >= %(min_terms)s
		ORDER BY m.unpaid_total DESC, unpaid_terms DESC
		""",
		values,
		as_dict=True,
	)
	for r in rows:
		r.unpaid_terms_amount = flt(r.unpaid_terms_amount)
		r.unpaid_total = flt(r.unpaid_total)
		_with_eth(r, "oldest_unpaid_from")

	return {
		"as_of": nowdate(),
		"as_of_ethiopian": _eth(nowdate()),
		"members_matching": len(rows),
		"total_unpaid_terms_amount": _money(sum(r.unpaid_terms_amount for r in rows)),
		"total_unpaid_including_penalties": _money(sum(r.unpaid_total for r in rows)),
		"note": "unpaid_total also includes unpaid penalties/other payments; unpaid_terms_amount is monthly fees only.",
		"members": rows[:limit],
		"truncated": len(rows) > limit,
	}


def get_member_payment_history(member, from_date=None, to_date=None):
	name = _resolve_member(member)
	doc = frappe.get_doc("Member", name)
	doc.check_permission("read")
	start, end = _range(from_date, to_date)

	def in_range(d):
		if not d:
			return start is None
		d = getdate(d)
		return (start is None or d >= start) and d <= end

	monthly = [
		_with_eth(
			{
				"start_date": t.start_date,
				"end_date": t.end_date,
				"amount": flt(t.amount),
				"is_paid": bool(t.is_paid),
				"penalized": bool(t.penalized),
				"payment_reference": t.payment_reference_number or t.payment_detail,
			},
			"start_date",
			"end_date",
		)
		for t in sorted(doc.monthly_payments or [], key=lambda t: t.start_date or date.min)
		if in_range(t.start_date)
	]
	other = [
		_with_eth(
			{
				"reason": p.reason,
				"amount": flt(p.amount),
				"status": p.status,
				"created_date": p.created_date,
				"payment_reference": p.payment_reference_number or p.payment_detail,
			},
			"created_date",
		)
		for p in doc.other_payments or []
		if in_range(p.created_date)
	]

	result = {
		"member_id": doc.name,
		"full_name": doc.full_name,
		"period": _period(start, end),
		"monthly_terms": monthly,
		"other_payments": other,
	}

	if _can_read("Membership Income"):
		filters = [["member", "=", name], ["docstatus", "=", 1], ["time", "<=", f"{end} 23:59:59"]]
		if start:
			filters.append(["time", ">=", f"{start} 00:00:00"])
		receipts = frappe.get_list(
			"Membership Income",
			filters=filters,
			fields=["name", "time", "amount", "bank", "transaction_id"],
			order_by="time asc",
			limit_page_length=MAX_LIMIT,
		)
		for r in receipts:
			r.amount = flt(r.amount)
			r.time_ethiopian = _eth(r.time)
		result["payments_received"] = receipts
		result["payments_received_total"] = _money(sum(r.amount for r in receipts))
	else:
		result["payments_received"] = "omitted: no permission to read Membership Income"
	return result


def financial_summary(from_date=None, to_date=None):
	start, end = _range(from_date, to_date, default_from=get_first_day(nowdate()))
	values = {"start": start, "end": end}
	by_bank: dict[str, dict] = {}
	omitted = []

	def bucket(bank):
		return by_bank.setdefault(
			bank or "(no bank account)",
			{"membership_income": 0.0, "other_income": 0.0, "expenses": 0.0},
		)

	sources = [
		(
			"Membership Income",
			"membership_income",
			"SELECT bank AS bank, SUM(amount) AS total, COUNT(*) AS n FROM `tabMembership Income` "
			"WHERE docstatus = 1 AND DATE(time) BETWEEN %(start)s AND %(end)s GROUP BY bank",
		),
		(
			"Other Income",
			"other_income",
			"SELECT bank_account AS bank, SUM(amount) AS total, COUNT(*) AS n FROM `tabOther Income` "
			"WHERE docstatus = 1 AND date BETWEEN %(start)s AND %(end)s GROUP BY bank_account",
		),
		(
			"Expense",
			"expenses",
			"SELECT bank_account AS bank, SUM(amount) AS total, COUNT(*) AS n FROM `tabExpense` "
			"WHERE docstatus = 1 AND date BETWEEN %(start)s AND %(end)s GROUP BY bank_account",
		),
	]
	totals, counts = {}, {}
	for doctype, key, sql in sources:
		if not _can_read(doctype):
			omitted.append(doctype)
			continue
		rows = frappe.db.sql(sql, values, as_dict=True)
		totals[key] = _money(sum(flt(r.total) for r in rows))
		counts[key] = sum(r.n for r in rows)
		for r in rows:
			bucket(r.bank)[key] += flt(r.total)

	if len(omitted) == len(sources):
		raise ToolError("You do not have permission to read income or expense records.")

	income = totals.get("membership_income", 0.0) + totals.get("other_income", 0.0)
	result = {
		"period": _period(start, end),
		"membership_income": totals.get("membership_income"),
		"other_income": totals.get("other_income"),
		"total_income": _money(income),
		"expenses": totals.get("expenses"),
		"net": _money(income - totals.get("expenses", 0.0)),
		"document_counts": counts,
		"by_bank_account": [
			{"bank_account": bank, **{k: _money(v) for k, v in vals.items()}, "net": _money(
				vals["membership_income"] + vals["other_income"] - vals["expenses"]
			)}
			for bank, vals in sorted(by_bank.items())
		],
		"note": "Only submitted documents are counted. Internal transfers between bank accounts are excluded.",
	}
	if omitted:
		result["omitted_no_permission"] = omitted
		result["note"] += " Some sources were omitted (no permission), so totals are partial."
	return result


def expenses_by_category(from_date=None, to_date=None):
	_require_read("Expense")
	start, end = _range(from_date, to_date, default_from=get_first_day(nowdate()))
	values = {"start": start, "end": end}
	rows = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(ei.category, ''), 'Uncategorized') AS category,
			SUM(ei.amount) AS amount,
			COUNT(DISTINCT e.name) AS expense_documents,
			COUNT(ei.name) AS line_items
		FROM `tabExpense` e
		JOIN `tabExpense Item` ei ON ei.parent = e.name AND ei.parenttype = 'Expense'
		WHERE e.docstatus = 1 AND e.date BETWEEN %(start)s AND %(end)s
		GROUP BY COALESCE(NULLIF(ei.category, ''), 'Uncategorized')
		ORDER BY amount DESC
		""",
		values,
		as_dict=True,
	)
	header_total = _money(
		frappe.db.sql(
			"SELECT SUM(amount) FROM `tabExpense` WHERE docstatus = 1 AND date BETWEEN %(start)s AND %(end)s",
			values,
		)[0][0]
	)
	items_total = _money(sum(flt(r.amount) for r in rows))
	for r in rows:
		r.amount = flt(r.amount)
		r.share_percent = round(r.amount * 100 / items_total, 1) if items_total else 0
	result = {
		"period": _period(start, end),
		"categories": rows,
		"total_from_items": items_total,
		"total_from_expense_documents": header_total,
	}
	if abs(items_total - header_total) > 0.01:
		result["note"] = (
			"Line-item total differs from the expense documents' total; some expenses may have "
			"no items or item amounts that do not add up to the document amount."
		)
	return result


def search_bank_transactions(
	query=None, from_date=None, to_date=None, type=None, unmatched_only=False, limit=50
):
	_require_read("Bank Transaction")
	limit = _limit(limit, 50)
	start, end = _range(from_date, to_date)
	filters = [["date", "<=", end]]
	if start:
		filters.append(["date", ">=", start])
	if type:
		if type not in ("Credit", "Debit"):
			raise ToolError("type must be 'Credit' or 'Debit'")
		filters.append(["type", "=", type])
	if unmatched_only:
		filters.append(["reference_name", "is", "not set"])
	or_filters = None
	if query:
		like = f"%{str(query).strip()}%"
		or_filters = [
			["sender_name", "like", like],
			["transaction_id", "like", like],
			["bank_account_holder", "like", like],
			["message", "like", like],
		]
	rows = frappe.get_list(
		"Bank Transaction",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"date",
			"type",
			"amount",
			"sender_name",
			"transaction_id",
			"bank_account_holder",
			"reference_doctype",
			"reference_name",
		],
		order_by="date desc, creation desc",
		limit_page_length=limit + 1,
	)
	truncated = len(rows) > limit
	rows = rows[:limit]
	for r in rows:
		r.amount = flt(r.amount)
		r.date_ethiopian = _eth(r.date)
		r.matched = bool(r.reference_name)
	return {
		"period": _period(start, end),
		"transactions": rows,
		"truncated": truncated,
		"returned_credit_total": _money(sum(r.amount for r in rows if r.type == "Credit")),
		"returned_debit_total": _money(sum(r.amount for r in rows if r.type == "Debit")),
		"note": "Totals cover only the returned rows." if truncated else None,
	}


def bank_balances():
	_require_read("Bank Account Balance")
	rows = frappe.get_list(
		"Bank Account Balance",
		fields=["name", "bank_name", "account_number", "remaining_balance"],
		order_by="bank_name asc",
		limit_page_length=MAX_LIMIT,
	)
	for r in rows:
		r.remaining_balance = flt(r.remaining_balance)
		acct = (r.account_number or "").strip()
		r.account_number = f"****{acct[-4:]}" if len(acct) > 4 else acct
	return {
		"as_of": nowdate(),
		"accounts": rows,
		"total_balance": _money(sum(r.remaining_balance for r in rows)),
	}


# --------------------------------------------------------------------------- registry

_DATE = {"type": "string", "format": "date", "description": "YYYY-MM-DD (Gregorian)"}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT}
_MEMBER = {"type": "string", "description": "Member ID, phone number, or full name"}

_TOOL_LIST = [
	Tool(
		name="search_members",
		title="Search members",
		description="Find members by name, nickname, phone or member ID. Returns basic info and unpaid totals.",
		input_schema={
			"type": "object",
			"properties": {
				"query": {"type": "string", "description": "Part of a name, nickname, phone or ID"},
				"status": {"type": "string", "enum": MEMBER_STATUSES},
				"limit": {**_LIMIT, "default": 20},
			},
		},
		handler=search_members,
	),
	Tool(
		name="get_member",
		title="Get member",
		description=(
			"Profile and balance for one member: status, fee, total received, unpaid total, credit balance, "
			"and the list of unpaid monthly terms and unpaid penalties/other payments."
		),
		input_schema={"type": "object", "properties": {"member": _MEMBER}, "required": ["member"]},
		handler=get_member,
	),
	Tool(
		name="list_members_with_arrears",
		title="Members with arrears",
		description=(
			"Members who owe monthly fees, sorted by amount owed. Use for 'who hasn't paid', "
			"'who is N months behind', and total outstanding arrears."
		),
		input_schema={
			"type": "object",
			"properties": {
				"min_unpaid_terms": {
					"type": "integer",
					"minimum": 1,
					"default": 1,
					"description": "Only members with at least this many unpaid monthly terms",
				},
				"status": {"type": "string", "enum": [*MEMBER_STATUSES, "Any"], "default": "Active"},
				"overdue_only": {
					"type": "boolean",
					"default": True,
					"description": "Count only terms whose end date has passed",
				},
				"limit": {**_LIMIT, "default": 50},
			},
		},
		handler=list_members_with_arrears,
	),
	Tool(
		name="get_member_payment_history",
		title="Member payment history",
		description=(
			"Monthly terms, penalties/other payments, and submitted payments received for one member, "
			"optionally limited to a date range."
		),
		input_schema={
			"type": "object",
			"properties": {"member": _MEMBER, "from_date": _DATE, "to_date": _DATE},
			"required": ["member"],
		},
		handler=get_member_payment_history,
	),
	Tool(
		name="financial_summary",
		title="Financial summary",
		description=(
			"Income (membership + other), expenses and net for a period, in total and per bank account. "
			"Defaults to the current month to date."
		),
		input_schema={"type": "object", "properties": {"from_date": _DATE, "to_date": _DATE}},
		handler=financial_summary,
	),
	Tool(
		name="expenses_by_category",
		title="Expenses by category",
		description="Submitted expenses for a period grouped by expense category, with share of total.",
		input_schema={"type": "object", "properties": {"from_date": _DATE, "to_date": _DATE}},
		handler=expenses_by_category,
	),
	Tool(
		name="search_bank_transactions",
		title="Search bank transactions",
		description=(
			"Search imported bank transactions (from bank SMS) by sender, transaction ID or text. "
			"Set unmatched_only to find transactions not yet linked to an income/expense record."
		),
		input_schema={
			"type": "object",
			"properties": {
				"query": {"type": "string"},
				"from_date": _DATE,
				"to_date": _DATE,
				"type": {"type": "string", "enum": ["Credit", "Debit"]},
				"unmatched_only": {"type": "boolean", "default": False},
				"limit": {**_LIMIT, "default": 50},
			},
		},
		handler=search_bank_transactions,
	),
	Tool(
		name="bank_balances",
		title="Bank balances",
		description="Current recorded balance of each bank account and the overall total.",
		input_schema={"type": "object", "properties": {}},
		handler=bank_balances,
	),
]

TOOLS = {t.name: t for t in _TOOL_LIST}
