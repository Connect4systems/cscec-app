from __future__ import annotations

import frappe
from frappe import _
from typing import Dict, List, Any, Optional

# ============================================================
# CONFIG
# ============================================================

COST_CODE_DOCTYPE = "Cost Code"

DOCMAP: Dict[str, Dict[str, Any]] = {
    # Uses custom_cost_code_id in child table
    "Stock Entry": {
        "parent": "Stock Entry",
        "child": "Stock Entry Detail",
        "date_field": "posting_date",
        "project_field": "project",
        "cc_field_child": "custom_cost_code_id",
        "item_field": "item_code",
        "qty_field": "qty",
        "uom_field": "uom",
        "rate_expr": "COALESCE(child.basic_rate, child.valuation_rate)",
        "amount_expr": "COALESCE(child.basic_rate, child.valuation_rate) * child.qty",
        "docstatus": 1,
    },
    "Purchase Order": {
        "parent": "Purchase Order",
        "child": "Purchase Order Item",
        "date_field": "transaction_date",
        "project_field": "project",
        "cc_field_child": "custom_cost_code_id",
        "item_field": "item_code",
        "qty_field": "qty",
        "uom_field": "uom",
        "rate_expr": "child.rate",
        "amount_expr": "child.amount",
        "docstatus": 1,
    },
}


def execute(filters=None):
    filters = filters or {}
    doctype = (filters.get("doctype") or "Stock Entry").strip()
    if doctype not in DOCMAP:
        frappe.throw(_("Unsupported Doctype: {0}").format(doctype))

    columns = get_columns()
    rows = fetch_line_rows(doctype, filters)
    data = build_tree_rows(rows, filters)
    return columns, data


def get_columns() -> List[Dict[str, Any]]:
    # align="left" لكل الأعمدة
    return [
        {
            "label": _("Voucher Type"),
            "fieldname": "voucher_type",
            "fieldtype": "Data",
            "width": 120,
            "hidden": 1,
            "align": "left",
        },
        {
            "label": _("Cost Code"),
            "fieldname": "cost_code",
            "fieldtype": "Link",
            "options": COST_CODE_DOCTYPE,
            "width": 200,
            "align": "left",
        },
        {
            "label": _("Cost Code Description"),
            "fieldname": "cost_code_description",
            "fieldtype": "Data",
            "width": 250,
            "align": "left",
        },
        {
            "label": _("Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
            "align": "left",
        },
        {
            "label": _("Transaction"),
            "fieldname": "transaction",
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 180,
            "align": "left",
        },
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 160,
            "align": "left",
        },
        {
            "label": _("Qty"),
            "fieldname": "qty",
            "fieldtype": "Float",
            "width": 90,
            "precision": 2,
            "align": "left",
        },
        {
            "label": _("UOM"),
            "fieldname": "uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 90,
            "align": "left",
        },
        {
            "label": _("Rate"),
            "fieldname": "rate",
            "fieldtype": "Currency",
            "width": 110,
            "align": "left",
        },
        {
            "label": _("Amount"),
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 130,
            "align": "left",
        },
    ]


def fetch_line_rows(doctype: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    m = DOCMAP[doctype]
    date_field = m["date_field"]
    project_field = m.get("project_field")
    cc_field_child = m["cc_field_child"]
    item_field = m["item_field"]
    qty_field = m["qty_field"]
    uom_field = m["uom_field"]
    rate_expr = m["rate_expr"]
    amount_expr = m["amount_expr"]

    where: List[str] = ["p.docstatus = %(docstatus)s"]
    params: Dict[str, Any] = {"docstatus": m["docstatus"]}

    if filters.get("from_date"):
        where.append(f"p.{date_field} >= %(from_date)s")
        params["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        where.append(f"p.{date_field} <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    if filters.get("project") and project_field:
        where.append(f"p.{project_field} = %(project)s")
        params["project"] = filters["project"]

    if filters.get("cost_code"):
        node = frappe.db.get_value(
            COST_CODE_DOCTYPE,
            filters["cost_code"],
            ["lft", "rgt"],
            as_dict=True,
        )
        if node:
            where.append(
                f"""child.{cc_field_child} IN (
                        SELECT name FROM `tab{COST_CODE_DOCTYPE}`
                        WHERE lft >= %(lft)s AND rgt <= %(rgt)s
                    )"""
            )
            params.update({"lft": node.lft, "rgt": node.rgt})
        else:
            where.append("1 = 0")

    where_clause = " AND ".join(where)

    sql = f"""
        SELECT
            %(voucher_type)s                AS voucher_type,
            child.{cc_field_child}          AS cost_code,
            cc.des                          AS cost_code_description,
            p.name                          AS transaction,
            p.{date_field}                  AS posting_date,
            child.{item_field}              AS item_code,
            child.{qty_field}               AS qty,
            child.{uom_field}               AS uom,
            {rate_expr}                     AS rate,
            {amount_expr}                   AS amount
        FROM `tab{m['parent']}` p
        JOIN `tab{m['child']}` child
            ON child.parent = p.name
        LEFT JOIN `tab{COST_CODE_DOCTYPE}` cc
            ON cc.name = child.{cc_field_child}
        WHERE {where_clause}
        ORDER BY
            child.{cc_field_child} IS NULL,
            p.{date_field},
            p.name
    """

    params["voucher_type"] = m["parent"]
    return frappe.db.sql(sql, params, as_dict=True)


def build_tree_rows(
    line_rows: List[Dict[str, Any]], filters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    if not line_rows:
        return []

    from collections import defaultdict

    data: List[Dict[str, Any]] = []
    filter_cc = (filters.get("cost_code") or "").strip() or None

    # map cost_code -> description from detail rows
    code_desc: Dict[str, str] = {}
    for r in line_rows:
        cc = r.get("cost_code")
        if cc and cc not in code_desc:
            code_desc[cc] = r.get("cost_code_description") or ""

    # إذا فيه Cost Code في الفلتر → جروب واحد للأب + تفاصيل تحته
    if filter_cc:
        groups: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
        for r in line_rows:
            if r.get("cost_code"):
                groups[filter_cc].append(r)
            else:
                groups[None].append(r)

        totals: Dict[Optional[str], float] = {
            cc: sum((row.get("amount") or 0) for row in rows)
            for cc, rows in groups.items()
        }

        tree_info = load_tree_info_with_ancestors([filter_cc])
        ordered: List[Optional[str]] = [filter_cc]
        if None in groups:
            ordered.append(None)

        for cc in ordered:
            if cc:
                depth = tree_depth(cc, tree_info)
                data.append(
                    {
                        "voucher_type": "",
                        "cost_code": cc,
                        "cost_code_description": code_desc.get(cc, ""),
                        "posting_date": None,
                        "transaction": None,
                        "item_code": None,
                        "qty": None,
                        "uom": None,
                        "rate": None,
                        "amount": totals.get(cc, 0),
                        "indent": depth,
                        "is_group": 1,
                    }
                )
            else:
                data.append(
                    {
                        "voucher_type": "",
                        "cost_code": _("(No Cost Code)"),
                        "cost_code_description": "",
                        "posting_date": None,
                        "transaction": None,
                        "item_code": None,
                        "qty": None,
                        "uom": None,
                        "rate": None,
                        "amount": totals.get(None, 0),
                        "indent": 0,
                        "is_group": 1,
                    }
                )

            for row in groups.get(cc, []):
                child_indent = 1 if cc is None else (tree_depth(filter_cc, tree_info) + 1)
                line = dict(row)
                line["indent"] = child_indent
                line["is_group"] = 0
                data.append(line)

        return data

    # بدون فلتر Cost Code → جروب لكل كود زي القديم
    groups2: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    for r in line_rows:
        groups2[r.get("cost_code")].append(r)

    totals2: Dict[Optional[str], float] = {
        cc: sum((row.get("amount") or 0) for row in rows)
        for cc, rows in groups2.items()
    }

    cc_names = [cc for cc in groups2.keys() if cc]
    tree_info2 = load_tree_info_with_ancestors(cc_names) if cc_names else {}

    ordered2: List[Optional[str]] = sorted(
        cc_names,
        key=lambda n: tree_info2.get(n, {}).get("lft", 10**9),
    )
    if None in groups2:
        ordered2.append(None)

    for cc in ordered2:
        if cc:
            depth = tree_depth(cc, tree_info2)
            data.append(
                {
                    "voucher_type": "",
                    "cost_code": cc,
                    "cost_code_description": code_desc.get(cc, ""),
                    "posting_date": None,
                    "transaction": None,
                    "item_code": None,
                    "qty": None,
                    "uom": None,
                    "rate": None,
                    "amount": totals2.get(cc, 0),
                    "indent": depth,
                    "is_group": 1,
                }
            )
        else:
            data.append(
                {
                    "voucher_type": "",
                    "cost_code": _("(No Cost Code)"),
                    "cost_code_description": "",
                    "posting_date": None,
                    "transaction": None,
                    "item_code": None,
                    "qty": None,
                    "uom": None,
                    "rate": None,
                    "amount": totals2.get(None, 0),
                    "indent": 0,
                    "is_group": 1,
                }
            )

        for row in groups2[cc]:
            child_indent = 1 if cc is None else tree_depth(cc, tree_info2) + 1
            line = dict(row)
            line["indent"] = child_indent
            line["is_group"] = 0
            data.append(line)

    return data


def load_tree_info_with_ancestors(names: List[str]) -> Dict[str, Dict[str, Any]]:
    if not names:
        return {}

    info: Dict[str, Dict[str, Any]] = {}

    rows = frappe.db.sql(
        f"""
        SELECT
            name,
            parent_{frappe.scrub(COST_CODE_DOCTYPE)} AS parent,
            lft,
            rgt
        FROM `tab{COST_CODE_DOCTYPE}`
        WHERE name IN %(names)s
        """,
        {"names": list(set(names))},
        as_dict=True,
    )
    for d in rows:
        info[d.name] = {"parent": d.parent, "lft": d.lft, "rgt": d.rgt}

    changed = True
    while changed:
        missing = [
            v["parent"]
            for v in info.values()
            if v.get("parent") and v["parent"] not in info
        ]
        missing = list(set(missing))
        if not missing:
            break

        rows = frappe.db.sql(
            f"""
            SELECT
                name,
                parent_{frappe.scrub(COST_CODE_DOCTYPE)} AS parent,
                lft,
                rgt
            FROM `tab{COST_CODE_DOCTYPE}`
            WHERE name IN %(names)s
            """,
            {"names": missing},
            as_dict=True,
        )
        changed = False
        for d in rows:
            if d.name not in info:
                info[d.name] = {"parent": d.parent, "lft": d.lft, "rgt": d.rgt}
                changed = True

    return info


def tree_depth(name: str, info: Dict[str, Dict[str, Any]]) -> int:
    depth = 0
    cur = name
    seen = set()

    while cur and cur in info and cur not in seen:
        seen.add(cur)
        parent = info[cur].get("parent")
        if parent:
            depth += 1
        cur = parent

    return depth
