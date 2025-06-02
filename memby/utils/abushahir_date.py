import frappe
from ethiopian_date import EthiopianDateConverter

@frappe.whitelist()
def to_abushahir(date):
    if not date:
        return ""
    
    # Make sure input is datetime.date
    if isinstance(date, str):
        from frappe.utils import getdate
        date = getdate(date)

    eth_date = EthiopianDateConverter.to_ethiopian(date.year, date.month, date.day)

    # eth_date is a datetime.date object
    return f"{eth_date.year}-{eth_date.month:02d}-{eth_date.day:02d}"
