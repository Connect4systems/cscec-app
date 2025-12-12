/* globals frappe */

frappe.query_reports["Cost Report"] = {
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
      options: ["Stock Entry", "Purchase Order", "Purchase Receipt"],
      default: "Stock Entry",
      reqd: 1
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
    // القيمة الافتراضية من فريب
    value = default_formatter(value, row, column, data);

    // style أساسي لليسار
    let style = "text-align:left; padding:4px 6px;";

    // خلفية وألوان
    if (data && data.is_group) {
      // صفوف كود التكلفة (Group)
      style += "background:#eef4ff; font-weight:600; color:#1e3a8a; border-bottom:1px solid #d0d7ff;";
    } else {
      // صفوف التفاصيل
      style += "background:#ffffff;";
    }

    // Indent للأعمدة الأساسية في الشجرة
    if (["cost_code", "transaction", "item_code"].includes(column.fieldname)) {
      const indent = (data && data.indent ? data.indent : 0) * 20;
      style += ` padding-left:${indent}px;`;
    }

    return `<div style="${style}">${value}</div>`;
  }
};
