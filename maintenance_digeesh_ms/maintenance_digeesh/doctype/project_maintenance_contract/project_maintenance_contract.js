frappe.ui.form.on('Project Maintenance Contract', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Update Contract Status'), function() {
                let d = new frappe.ui.Dialog({
                    title: 'Update Contract Status',
                    fields: [
                        {
                            label: 'New Status',
                            fieldname: 'new_status',
                            fieldtype: 'Select',
                            options: 'Completed\nTerminated',
                            reqd: 1
                        }
                    ],
                    primary_action_label: 'Update',
                    primary_action(values) {
                        frappe.call({
                            method: 'maintenance_digeesh_ms.maintenance_digeesh.doctype.project_maintenance_contract.project_maintenance_contract.update_contract_status',
                            args: {
                                docname: frm.doc.name,
                                new_status: values.new_status
                            },
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint(r.message.message);
                                    frm.reload_doc();
                                }
                            }
                        });
                        d.hide();
                    }
                });
                d.show();
            });

            let total_invoiced = frm.doc.total_invoiced_amount || 0;
            let total_contract = frm.doc.total_contract_value || 0;
            let pending_balance = frm.doc.pending_balance || 0;
            let status = frm.doc.status || '';

            if (pending_balance > 0 && 
                total_contract > 0 && 
                status === 'Active' && 
                (status !== 'Completed' && status !== 'Terminated')) {
                
                frm.add_custom_button(__('Generate Next Invoice'), function() {
                    frappe.call({
                        method: 'maintenance_digeesh_ms.maintenance_digeesh.doctype.project_maintenance_contract.project_maintenance_contract.generate_next_invoice',
                        args: {
                            docname: frm.doc.name
                        },
                        callback: function(r) {
                            if (r.message) {
                                if (r.message.success) {
                                    frappe.msgprint(r.message.message);
                                    frm.reload_doc();
                                } else {
                                    frappe.msgprint({
                                        title: 'Error',
                                        message: r.message.message,
                                        indicator: 'red'
                                    });
                                }
                            }
                        }
                    });
                });
            }
        }

        if (!frm.doc.created_by && frm.is_new()) {
            frm.set_value('created_by', frappe.session.user_fullname || frappe.session.user);
        }
        if (!frm.doc.created_on && frm.is_new()) {
            frm.set_value('created_on', frappe.datetime.get_today());
        }
    },

    onload: function(frm) {
        frm.fields_dict['service_items'].grid.get_field('service_item').get_query = function() {
            return {
                filters: {
                    is_stock_item: 0,
                    disabled: 0,
                    has_variants: 0
                }
            };
        };

        frm.fields_dict['service_items'].grid.get_field('uom').get_query = function() {
            return {
                filters: {
                    name: ['in', ['Hrs', 'Visit', 'Session']]
                }
            };
        };
    },

    before_workflow_action: async function (frm) {
        if (frm.selected_workflow_action == "Submit") {
            return new Promise((resolve, reject) => {
                frappe.dom.unfreeze();

                const d = new frappe.ui.Dialog({
                    title: "Confirm Submission",
                    fields: [
                        {
                            fieldtype: "HTML",
                            fieldname: "confirmation_html",
                            options: `
                                <b>
                                    Are you sure you want to <u>${frm.selected_workflow_action}</u>?<br><br>
                                    Contract Title: ${frm.doc.contract_title}<br>
                                    Contract Type: ${frm.doc.contract_type}<br>
                                    Total Estimated Hours: ${frm.doc.total_estimated_hours}<br>
                                    Total Contract Value: ${frm.doc.total_contract_value}<br>
                                </b>
                            `
                        }
                    ],
                    primary_action_label: "Confirm",
                    primary_action: () => {
                        d.hide();
                        resolve();
                    },
                    secondary_action_label: "Back",
                    secondary_action: () => {
                        d.hide();
                        reject("Action cancelled by user.");
                    }
                });

                d.show();
            });
        }
    }
});

frappe.ui.form.on('Maintenance Task', {
    service_item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.service_item) {
            frappe.call({
                method: 'maintenance_digeesh_ms.maintenance_digeesh.doctype.project_maintenance_contract.project_maintenance_contract.get_service_item_details',
                args: {
                    item_code: row.service_item
                },
                callback: function(r) {
                    if (r.message) {
                        if (!r.message.valid) {
                            frappe.msgprint('Please select a valid service item.');
                            frappe.model.set_value(cdt, cdn, 'service_item', '');
                        } else {
                            frappe.model.set_value(cdt, cdn, 'description', r.message.description);
                            if (r.message.uom && ['Hrs', 'Visit', 'Session'].includes(r.message.uom)) {
                                frappe.model.set_value(cdt, cdn, 'uom', r.message.uom);
                            } else {
                                frappe.model.set_value(cdt, cdn, 'uom', 'Hrs');
                            }
                        }
                    }
                }
            });
        }
    },

    estimated_hours: function(frm, cdt, cdn) {
        calculate_total_cost(frm, cdt, cdn);
    },

    rate_per_hour: function(frm, cdt, cdn) {
        calculate_total_cost(frm, cdt, cdn);
    },

    service_items_remove: function(frm) {
        calculate_totals(frm);
    }
});

function calculate_total_cost(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
   
        frappe.model.set_value(cdt, cdn, 'total_cost', row.estimated_hours * row.rate_per_hour);
    
    calculate_totals(frm);
}

function calculate_totals(frm) {
    let total_hours = 0;
    let total_value = 0;

    (frm.doc.service_items || []).forEach(row => {
        total_hours += row.estimated_hours || 0;
        total_value += row.total_cost || 0;
    });

    frm.set_value('total_estimated_hours', total_hours);
    frm.set_value('total_contract_value', total_value);

    let total_invoiced = 0;
    (frm.doc.billing_schedule || []).forEach(row => {
        if (row.invoice_status === 'Paid') {
            total_invoiced += row.invoice_amount || 0;
        }
    });

    frm.set_value('total_invoiced_amount', total_invoiced);
    frm.set_value('pending_balance', total_value - total_invoiced);
}

frappe.ui.form.on('Billing Schedule', {
    invoice_status: function(frm) {
        calculate_totals(frm);
    },
    invoice_amount: function(frm) {
        calculate_totals(frm);
    },
    billing_schedule_remove: function(frm) {
        calculate_totals(frm);
    }
});