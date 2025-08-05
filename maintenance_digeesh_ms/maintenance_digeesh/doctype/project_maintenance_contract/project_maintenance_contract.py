import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, flt, today, add_months, getdate

class ProjectMaintenanceContract(Document):

    def validate(self):
        self.calculate_duration()
        self.calculate_totals()
        
        self.fetch_customer_details()
        self.validate_dates()
        self.set_created_fields()

    def before_submit(self):
        self.validate_before_submit()
        self.status = "Active"

    def set_created_fields(self):
        if not self.created_by:
            self.created_by = frappe.session.user_fullname or frappe.session.user
        if not self.created_on:
            self.created_on = today()

    def calculate_duration(self):
        if self.contract_start_date and self.contract_end_date:
            self.duration_in_days = date_diff(self.contract_end_date, self.contract_start_date)
            if self.duration_in_days < 0:
                frappe.throw("Contract End Date cannot be before Start Date")

    def calculate_totals(self):
        total_hours = 0
        total_value = 0

        for item in self.service_items or []:
            if item.estimated_hours and item.rate_per_hour:
                item.total_cost = flt(item.estimated_hours) * flt(item.rate_per_hour)
                total_hours += flt(item.estimated_hours)
                total_value += flt(item.total_cost)

        self.total_estimated_hours = total_hours
        self.total_contract_value = total_value

        total_invoiced = sum(
            [flt(row.invoice_amount) for row in self.billing_schedule or [] if row.invoice_status == "Paid"]
        )
        self.total_invoiced_amount = total_invoiced
        self.pending_balance = flt(self.total_contract_value) - flt(total_invoiced)

    def validate_contract_data(self):
        if flt(self.total_estimated_hours) == 0:
            frappe.throw("Total Estimated Hours cannot be zero")

        if flt(self.total_contract_value) == 0:
            frappe.throw("Total Contract Value cannot be zero")

        if flt(self.total_invoiced_amount) > flt(self.total_contract_value):
            frappe.throw("Invoiced amount cannot exceed total contract value")

    def validate_dates(self):
        if self.contract_start_date and self.contract_end_date:
            if getdate(self.contract_start_date) > getdate(self.contract_end_date):
                frappe.throw("Contract Start Date cannot be after End Date")

    def validate_before_submit(self):
        self.validate_contract_data()

        if not self.customer_name:
            frappe.throw("Customer Name is required before submission")

        if not self.contract_type:
            frappe.throw("Contract Type is required before submission")

        if not self.service_items or len(self.service_items) == 0:
            frappe.throw("At least one Service Item is required")

        for item in self.service_items:
            if not item.description:
                frappe.throw("Each Service Item must have a Description")

    def fetch_customer_details(self):
        if not self.customer_name:
            return

        if not self.customer_email or not self.customer_contact_number:
            contact = frappe.db.sql("""
                SELECT c.email_id, c.phone
                FROM `tabContact` c
                JOIN `tabDynamic Link` dl ON dl.parent = c.name
                WHERE dl.link_doctype = 'Customer'
                  AND dl.link_name = %s
                  AND dl.parenttype = 'Contact'
                ORDER BY c.creation DESC
                LIMIT 1
            """, (self.customer_name,), as_dict=True)

            if contact:
                contact = contact[0]
                if contact.get("email_id") and not self.customer_email:
                    self.customer_email = contact.email_id
                if contact.get("phone") and not self.customer_contact_number:
                    self.customer_contact_number = contact.phone

      


@frappe.whitelist()
def update_contract_status(docname, new_status):
    """Update contract status"""
    if new_status not in ["Completed", "Terminated"]:
        frappe.throw("Invalid status. Only 'Completed' or 'Terminated' allowed.")
    
    doc = frappe.get_doc("Project Maintenance Contract", docname)
    doc.db_set("status", new_status)

    return {"message": f"Contract status updated to {new_status}"}


@frappe.whitelist()
def create_billing_entry(docname, invoice_date, invoice_amount, invoice_status, remarks=None):
    """Create new billing entry for a submitted Project Maintenance Contract"""
    doc = frappe.get_doc("Project Maintenance Contract", docname)

    if doc.docstatus != 1:
        frappe.throw("Billing entries can only be added to submitted contracts.")

    remaining_balance = flt(doc.total_contract_value) - flt(doc.total_invoiced_amount)
    if flt(invoice_amount) > remaining_balance:
        frappe.throw(f"Invoice amount ({invoice_amount}) cannot exceed remaining balance ({remaining_balance})")

    existing_rows = frappe.get_all(
        "Billing Schedule",
        filters={"parent": docname, "parenttype": "Project Maintenance Contract"},
        fields=["idx"]
    )
    max_idx = max([row.idx for row in existing_rows], default=0)

    child = frappe.get_doc({
        "doctype": "Billing Schedule",
        "parent": doc.name,
        "parenttype": "Project Maintenance Contract",
        "parentfield": "billing_schedule",
        "invoice_date": invoice_date,
        "invoice_amount": flt(invoice_amount),
        "invoice_status": invoice_status,
        "remarks": remarks or "Manual invoice entry",
        "idx": max_idx + 1
    })
    child.flags.ignore_permissions = True
    child.flags.ignore_validate = True
    child.insert(ignore_permissions=True)

    billing_rows = frappe.get_all(
        "Billing Schedule",
        filters={"parent": docname, "parenttype": "Project Maintenance Contract", "invoice_status": "Paid"},
        fields=["invoice_amount"]
    )
    total_invoiced = sum(flt(row.invoice_amount) for row in billing_rows)

    frappe.db.set_value("Project Maintenance Contract", docname, "total_invoiced_amount", total_invoiced)
    frappe.db.set_value("Project Maintenance Contract", docname, "pending_balance", flt(doc.total_contract_value) - total_invoiced)

    return {"message": "Billing entry created successfully"}


@frappe.whitelist()
def generate_next_invoice(docname):
    """Auto-generate next invoice based on remaining balance"""
    try:
        doc = frappe.get_doc("Project Maintenance Contract", docname)
        
        if doc.docstatus != 1:
            return {"success": False, "message": "Invoice can only be generated for submitted contracts."}
        
        remaining_balance = flt(doc.total_contract_value) - flt(doc.total_invoiced_amount)
        if remaining_balance <= 0:
            return {"success": False, "message": "No remaining balance to invoice. Contract billing is completed."}
        
        if not doc.contract_type:
            return {"success": False, "message": "Contract Type is required to generate invoices."}
        
        if not doc.billing_schedule:
            next_date = doc.contract_start_date or today()
        else:
            last_invoice = max(doc.billing_schedule, key=lambda x: getdate(x.invoice_date))
            
            if doc.contract_type == "Monthly":
                next_date = add_months(last_invoice.invoice_date, 1)
            elif doc.contract_type == "Quarterly":
                next_date = add_months(last_invoice.invoice_date, 3)
            elif doc.contract_type == "Bi-Annual":
                next_date = add_months(last_invoice.invoice_date, 6)
            elif doc.contract_type == "Annual":
                next_date = add_months(last_invoice.invoice_date, 12)
            else:
                return {"success": False, "message": f"Invalid contract type: {doc.contract_type}"}
        
        if doc.contract_type == "Monthly":
            amount = flt(doc.total_contract_value) / 12
        elif doc.contract_type == "Quarterly":
            amount = flt(doc.total_contract_value) / 4
        elif doc.contract_type == "Bi-Annual":
            amount = flt(doc.total_contract_value) / 2
        elif doc.contract_type == "Annual":
            amount = flt(doc.total_contract_value)
        else:
            return {"success": False, "message": f"Cannot calculate amount for contract type: {doc.contract_type}"}
        
        if amount > remaining_balance:
            amount = remaining_balance
        
        existing_rows = frappe.get_all(
            "Billing Schedule",
            filters={"parent": docname, "parenttype": "Project Maintenance Contract"},
            fields=["idx"]
        )
        max_idx = max([row.idx for row in existing_rows], default=0)
        
        child = frappe.get_doc({
            "doctype": "Billing Schedule",
            "parent": doc.name,
            "parenttype": "Project Maintenance Contract",
            "parentfield": "billing_schedule",
            "invoice_date": next_date,
            "invoice_amount": amount,
            "invoice_status": "Pending",
            "remarks": f"Auto-generated {doc.contract_type.lower()} invoice",
            "idx": max_idx + 1
        })
        child.flags.ignore_permissions = True
        child.flags.ignore_validate = True
        child.insert(ignore_permissions=True)
        
        return {"success": True, "message": f"Next invoice generated successfully for {frappe.format(amount, {'fieldtype': 'Currency'})} due on {frappe.format(next_date, {'fieldtype': 'Date'})}"}
        
    except Exception as e:
        frappe.log_error(f"Error generating next invoice: {str(e)}", "Generate Next Invoice Error")
        return {"success": False, "message": f"Error generating invoice: {str(e)}"}


@frappe.whitelist()
def get_service_item_details(item_code):
    """Get service item details"""
    try:
        item = frappe.get_doc("Item", item_code)
        
        if item.is_stock_item:
            return {"valid": False}

        allowed_uoms = ['Hrs', 'Visit', 'Session']
        default_uom = 'Hrs'
        
        if item.stock_uom and item.stock_uom in allowed_uoms:
            uom = item.stock_uom
        else:
            uom = default_uom

        return {
            "valid": True,
            "description": item.description or item.item_name,
            "uom": uom
        }
    except:
        return {"valid": False}