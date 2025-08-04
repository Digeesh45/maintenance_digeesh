frappe.query_reports["Active Maintenance Contracts"] = {
	"filters": [
		{
			fieldname: "contract_type",
			label: "Contract Type",
			fieldtype: "Select",
			options: ["", "Monthly", "Quarterly", "Bi-Annual", "Annual"]
		},
		{
			fieldname: "start_date",
			label: "Start Date",
			fieldtype: "Date"
		},
		{
			fieldname: "end_date",
			label: "End Date",
			fieldtype: "Date"
		},
		{
			fieldname: "status",
			label: "Status",
			fieldtype: "MultiSelectList",
			get_data: () => ["Draft", "Active", "Completed", "Terminated"]
		}
	]
};
