# frappe-bench/apps/your_custom_app/your_custom_app/www/my_redirect_page.py

import frappe

def get_context(context):
    # You can add any server-side logic here if needed
    context.no_cache = True # Ensures the page is not cached