# memby/config/desktop.py

from frappe import _

def get_data():
    return [
        {
            "module_name": "Memby",
            "category": "Modules",
            "label": _("Memby"),
            "color": "blue",
            "icon": "octicon octicon-briefcase",
            "type": "module",
            "link": "memby"  # This is the route to the Page you created
        }
    ]
