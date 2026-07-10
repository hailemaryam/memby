import json

import frappe
import requests
from frappe.utils.password import get_decrypted_password

SMS_GATEWAY_URL = "https://api.sms-gate.app/3rdparty/v1/messages"
INVALID_PHONES = ("+2519", "+251")


def get_sms_credentials(throw=False):
	setting = frappe.get_single("Memby Setting")

	if not setting.enable_sms_notifications:
		if throw:
			frappe.throw("SMS notifications are disabled in Memby Setting")
		return None

	username = (setting.sms_gateway_user or "").strip()
	try:
		password = get_decrypted_password(
			"Memby Setting", "Memby Setting", "sms_gateway_password"
		)
	except Exception:
		password = None

	if not username or not password:
		if throw:
			frappe.throw("SMS gateway username or password is missing in Memby Setting")
		return None

	return {
		"setting": setting,
		"username": username,
		"password": password,
		"company_name": setting.company_name or "",
	}


def is_valid_phone(phone):
	phone = (phone or "").strip()
	return bool(phone) and phone not in INVALID_PHONES


@frappe.whitelist()
def send_payment_reminders(manual=0):
	is_manual = frappe.utils.cint(manual)
	creds = get_sms_credentials(throw=bool(is_manual))
	if not creds:
		frappe.logger().info(
			"SMS payment reminders skipped: notifications disabled or missing credentials"
		)
		return

	setting = creds["setting"]
	message_template = (setting.sms_payment_reminder_message or "").strip()
	if not message_template:
		if is_manual:
			frappe.throw("SMS payment reminder message is missing in Memby Setting")
		frappe.logger().info(
			"SMS payment reminders skipped: missing message template"
		)
		return

	members = frappe.get_all(
		"Member",
		filters={"status": "Active", "unpaid_total": [">", 0]},
		fields=["name", "full_name", "phone", "unpaid_total"],
	)

	result = broadcast_sms(
		members,
		message_template,
		creds,
		error_title_prefix="SMS payment reminder failed",
	)
	frappe.logger().info(
		f"SMS payment reminders finished: sent={result['sent']}, "
		f"failed={result['failed']}, total={result['total']}"
	)
	return result


@frappe.whitelist()
def send_custom_message(message):
	message = (message or "").strip()
	if not message:
		frappe.throw("Message text is required")

	creds = get_sms_credentials(throw=True)

	members = frappe.get_all(
		"Member",
		filters={"status": "Active"},
		fields=["name", "full_name", "phone", "unpaid_total"],
	)

	result = broadcast_sms(
		members,
		message,
		creds,
		error_title_prefix="Custom SMS failed",
	)
	frappe.logger().info(
		f"Custom SMS finished: sent={result['sent']}, "
		f"failed={result['failed']}, total={result['total']}"
	)
	return result


def broadcast_sms(members, message_template, creds, error_title_prefix):
	sent = 0
	failed = 0

	for member in members:
		phone = (member.phone or "").strip()
		if not is_valid_phone(phone):
			frappe.logger().info(
				f"SMS skipped for {member.name}: invalid phone"
			)
			continue

		text = format_message(
			message_template,
			full_name=member.full_name or member.name,
			unpaid_total=member.unpaid_total,
			company_name=creds["company_name"],
			phone=phone,
		)

		try:
			send_sms(creds["username"], creds["password"], text, phone)
			sent += 1
		except Exception:
			failed += 1
			frappe.log_error(
				title=f"{error_title_prefix} for {member.name}",
				message=frappe.get_traceback(),
			)

	return {"sent": sent, "failed": failed, "total": len(members)}


def format_message(template, full_name, unpaid_total, company_name, phone):
	return (
		template.replace("{full_name}", str(full_name))
		.replace("{unpaid_total}", str(unpaid_total))
		.replace("{company_name}", str(company_name))
		.replace("{phone}", str(phone))
	)


def send_sms(username, password, text, phone):
	payload = {
		"textMessage": {"text": text},
		"phoneNumbers": [phone],
	}
	response = requests.post(
		SMS_GATEWAY_URL,
		auth=(username, password),
		headers={"Content-Type": "application/json"},
		data=json.dumps(payload),
		timeout=30,
	)
	response.raise_for_status()
	return response
