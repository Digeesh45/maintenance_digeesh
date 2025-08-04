# Copyright (c) 2025, digeesh and contributors
# For license information, please see license.txt

# Copyright (c) 2025, digeesh and contributors
# License: MIT. See license.txt

import frappe
from frappe.utils import getdate

def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns():
	return [
		{"label": "Contract Title", "fieldname": "contract_title", "fieldtype": "Data", "width": 200},
		{"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Link", "options": "Customer", "width": 200},
		{"label": "Contract Type", "fieldname": "contract_type", "fieldtype": "Data", "width": 120},
		{"label": "Supervisor", "fieldname": "supervisor", "fieldtype": "Link", "options": "Employee", "width": 180},
		{"label": "Start Date", "fieldname": "contract_start_date", "fieldtype": "Date", "width": 120},
		{"label": "End Date", "fieldname": "contract_end_date", "fieldtype": "Date", "width": 120},
		{"label": "Total Contract Value", "fieldname": "total_contract_value", "fieldtype": "Currency", "width": 150},
		{"label": "Invoiced Amount", "fieldname": "total_invoiced_amount", "fieldtype": "Currency", "width": 150},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120}
	]


def get_data(filters):
    conditions = []

    if filters.get("contract_type"):
        conditions.append("pmc.contract_type = %(contract_type)s")

    if filters.get("start_date"):
        conditions.append("pmc.contract_start_date >= %(start_date)s")

    if filters.get("end_date"):
        conditions.append("pmc.contract_start_date <= %(end_date)s")

    if filters.get("status"):
        try:
            # Handles both list and string input
            if isinstance(filters["status"], str):
                status_list = [filters["status"]]
            else:
                status_list = filters["status"]

            conditions.append("pmc.status IN %(status)s")
            filters["status"] = tuple(status_list)
        except Exception as e:
            frappe.throw(f"Invalid status filter: {e}")

    condition_str = " AND ".join(conditions)
    if condition_str:
        condition_str = "WHERE " + condition_str

    query = f"""
        SELECT
            pmc.contract_title,
            pmc.customer_name,
            pmc.contract_type,
            pmc.supervisor,
            pmc.contract_start_date,
            pmc.contract_end_date,
            pmc.total_contract_value,
            pmc.total_invoiced_amount,
            pmc.status
        FROM `tabProject Maintenance Contract` pmc
        {condition_str}
        ORDER BY pmc.contract_start_date DESC
    """

    return frappe.db.sql(query, filters, as_dict=True)
