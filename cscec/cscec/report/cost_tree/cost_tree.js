/* globals frappe */

frappe.query_reports["Cost Tree"] = {
  filters: [
    {
      fieldname: "cost_code",
      label: __("Cost Code"),
      fieldtype: "Link",
      options: "Cost Code"
    },
    {
      fieldname: "doctype",
      label: __("Doctype"),
      fieldtype: "Select",
      options: "Stock Entry\nPurchase Order\nPurchase Receipt",
      default: "Purchase Order",
      reqd: 1
    },
    {
      fieldname: "item_code",
      label: __("Item"),
      fieldtype: "Link",
      options: "Item"
    },
    {
      fieldname: "from_date",
      label: __("From Date"),
      fieldtype: "Date",
      default: frappe.datetime.month_start()
    },
    {
      fieldname: "to_date",
      label: __("To Date"),
      fieldtype: "Date",
      default: frappe.datetime.month_end()
    },
    {
      fieldname: "project",
      label: __("Project"),
      fieldtype: "Link",
      options: "Project"
    }
  ],

  formatter(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    if (["cost_code", "transaction", "item_code"].includes(column.fieldname)) {
      var indent = (data && data.indent ? data.indent : 0) * 20;
      value = '<div style="padding-left:' + indent + 'px">' + value + "</div>";
    }

    if (data && data.is_group) {
      value = '<span style="font-weight:600">' + value + "</span>";
    }

    return value;
  }
};
