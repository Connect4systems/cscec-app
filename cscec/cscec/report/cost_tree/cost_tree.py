from __future__ import annotations
import frappe
from frappe import _
from typing import Dict, List, Any, Optional

# ==========================================
# CONFIG
# ==========================================

COST_CODE_DOCTYPE = "Cost Code"
DEFAULT_CC_FIELD_CHILD = "cost_code"  # child table link field to Cost Code

DOCMAP: Dict[str, Dict[str, Any]] = {
    # ---------- Stock Entry ----------
    "Stock Entry": {
        "parent": "Stock Entry",
        "child": "Stock Entry Detail",
        "date_field": "posting_date",
        "project_field": "project",
        "cc_field_child": DEFAULT_CC_FIELD_CHILD,
        "item_field": "item_code",
        "qty_field": "qty",
        "uom_field": "uom",
        "rate_expr": "COALESCE(child.basic_rate, child.valuation_rate)",
        "amount_expr": "COALESCE(child.basic_rate, child.valuation_rate) * child.qty",
        "docstatus": 1,
    },
    # ---------- Purchase Order ----------
    "Purchase Order": {
        "parent": "Purchase Order",
        "child": "Purchase Order Item",
        "date_field": "transaction_date",
        "project_field": "project",
        "cc_field_child": DEFAULT_CC_FIELD_CHILD,
        "item_field": "item_code",
        "qty_field": "qty",
        "uom_field": "uom",
        "rate_expr": "child.rate",
        "amount_expr": "child.rate * child.qty",
        "docstatus": 1,
    },
    # ---------- Purchase Receipt ----------
    "Purchase Receipt": {
        "parent": "Purchase Receipt",
        "child": "Purchase Receipt Item",
        "date_field": "posting_date",
        "project_field": "project",
        "cc_field_child": DEFAULT_CC_FIELD_CHILD,
        "item_field": "item_code",
        "qty_field": "qty",
        "uom_field": "uom",
        "rate_expr": "COALESCE(child.rate, child.valuation_rate)",
        "amount_expr": "COALESCE(child.rate, child.valuation_rate) * child.qty",
        "docstatus": 1,
    },
}


def execute(filters=None):
    """Main entry point for the report."""
    filters = frappe._dict(filters or {})
    doctype = (filters.get("doctype") or "Purchase Order").strip()

    if doctype not in DOCMAP:
        frappe.throw(_("Unsupported Doctype: {0}").format(doctype))

    columns = get_columns()
    rows = fetch_line_rows(doctype, filters)
    data = build_tree_rows(rows)
    return columns, data


# ==========================================
# COLUMNS
# ==========================================

def get_columns() -> List[Dict[str, Any]]:
    """Define report columns (all left aligned as requested)."""
    return [
        {
            "label": _("Voucher Type"),
            "fieldname": "voucher_type",
            "fieldtype": "Data",
            "width": 120,
            "hidden": 1,
        },
        {
            "label": _("Cost Code"),
            "fieldname": "cost_code",
            "fieldtype": "Link",
            "options": COST_CODE_DOCTYPE,
            "width": 260,
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
            "width": 140,
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


# ==========================================
# DATA FETCH
# ==========================================

def fetch_line_rows(doctype: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch raw transaction rows from child tables according to filters."""
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

    # Date range
    if filters.get("from_date"):
        where.append(f"p.{date_field} >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        where.append(f"p.{date_field} <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    # Project filter
    if filters.get("project") and project_field:
        where.append(f"p.{project_field} = %(project)s")
        params["project"] = filters["project"]

    # Item filter
    if filters.get("item_code"):
        where.append(f"child.{item_field} = %(item_code)s")
        params["item_code"] = filters["item_code"]

    # Cost Code filter:
    # - parent: "01.01.001.000" -> all children "01.01.001.xxx"
    # - leaf:   "100.035.012"   -> only 100.035.012 (no siblings)
    if filters.get("cost_code"):
        where.append(
            f"child.{cc_field_child} IS NOT NULL "
            f"AND child.{cc_field_child} LIKE %(cc_like)s"
        )
        params["cc_like"] = filters["cost_code"] + "%"

    where_clause = " AND ".join(where)

    sql = f"""
        SELECT
            %(doctype)s AS voucher_type,
            child.{cc_field_child} AS cost_code,
            p.name                  AS transaction,
            p.{date_field}          AS posting_date,
            child.{item_field}      AS item_code,
            child.{qty_field}       AS qty,
            child.{uom_field}       AS uom,
            {rate_expr}             AS rate,
            {amount_expr}           AS amount
        FROM `tab{m['parent']}` p
        JOIN `tab{m['child']}` child ON child.parent = p.name
        WHERE {where_clause}
        ORDER BY child.{cc_field_child},
                 p.{date_field},
                 p.name
    """

    params["doctype"] = m["parent"]
    return frappe.db.sql(sql, params, as_dict=True)


# ==========================================
# TREE BUILDING
# ==========================================

def build_tree_rows(line_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build tree-style rows:
    - show full parent chain (like Cost Code tree)
    - each parent row shows subtotal of all its descendants
    - final TOTAL row at bottom for all visible detail rows
    """
    if not line_rows:
        return []

    from collections import defaultdict

    groups: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
    for r in line_rows:
        groups[r.get("cost_code")].append(r)

    # cost codes that appear on transactions
    cc_with_data = [cc for cc in groups.keys() if cc]

    # load tree info for these codes + their ancestors
    tree_info = load_tree_info_with_ancestors(cc_with_data) if cc_with_data else {}

    # subtree_totals[code] = sum of amounts for this code + all descendants
    subtree_totals: Dict[Optional[str], float] = {}

    for row in line_rows:
        amount = row.get("amount") or 0
        cc = row.get("cost_code")
        cur = cc
        # bubble amount up through all ancestors
        while cur:
            subtree_totals[cur] = subtree_totals.get(cur, 0) + amount
            info = tree_info.get(cur)
            cur = info.get("parent") if info else None

    # handle rows without cost code (should be rare)
    if None in groups:
        subtree_totals[None] = sum((r.get("amount") or 0) for r in groups[None])

    # all codes we want to show = all nodes in tree_info
    all_nodes = list(tree_info.keys())

    # order by lft to respect tree hierarchy
    ordered = sorted(all_nodes, key=lambda n: tree_info[n]["lft"])

    # put "no cost code" group at end if present
    if None in groups:
        ordered.append(None)

    data: List[Dict[str, Any]] = []

    for cc in ordered:
        # ----- group (header) row -----
        if cc is not None:
            depth = tree_depth(cc, tree_info)
            data.append({
                "voucher_type": "",
                "cost_code": cc,
                "posting_date": None,
                "transaction": None,
                "item_code": None,
                "qty": None,
                "uom": None,
                "rate": None,
                "amount": subtree_totals.get(cc, 0),
                "indent": depth,
                "is_group": 1,
            })
        else:
            data.append({
                "voucher_type": "",
                "cost_code": _("(No Cost Code)"),
                "posting_date": None,
                "transaction": None,
                "item_code": None,
                "qty": None,
                "uom": None,
                "rate": None,
                "amount": subtree_totals.get(None, 0),
                "indent": 0,
                "is_group": 1,
            })

        # ----- detail rows directly under this cost code -----
        for row in groups.get(cc, []):
            child_indent = 1 if cc is None else tree_depth(cc, tree_info) + 1
            line = dict(row)
            line["indent"] = child_indent
            line["is_group"] = 0
            data.append(line)

    # ----- GRAND TOTAL row (all detail lines) -----
    grand_total = sum(
        (row.get("amount") or 0)
        for row in data
        if not row.get("is_group")
    )
    if grand_total:
        data.append({
            "voucher_type": "",
            "cost_code": _("TOTAL"),
            "posting_date": None,
            "transaction": None,
            "item_code": None,
            "qty": None,
            "uom": None,
            "rate": None,
            "amount": grand_total,
            "indent": 0,
            "is_group": 1,
        })

    return data


# ==========================================
# TREE HELPERS
# ==========================================

def load_tree_info_with_ancestors(names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Return {code: {parent, lft, rgt}} for all given codes + ALL their ancestors."""
    if not names:
        return {}

    info: Dict[str, Dict[str, Any]] = {}

    # first load all codes that appear directly
    rows = frappe.db.sql(
        f"""
        SELECT name,
               parent_{frappe.scrub(COST_CODE_DOCTYPE)} AS parent,
               lft, rgt
        FROM `tab{COST_CODE_DOCTYPE}`
        WHERE name IN %(names)s
        """,
        {"names": list(set(names))},
        as_dict=True,
    )
    for d in rows:
        info[d.name] = {"parent": d.parent, "lft": d.lft, "rgt": d.rgt}

    # iteratively pull missing ancestors
    changed = True
    while changed:
        missing = [
            v["parent"]
            for v in info.values()
            if v["parent"] and v["parent"] not in info
        ]
        missing = list(set(missing))
        if not missing:
            break

        rows = frappe.db.sql(
            f"""
            SELECT name,
                   parent_{frappe.scrub(COST_CODE_DOCTYPE)} AS parent,
                   lft, rgt
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
    """Return depth level in Cost Code tree (root = 0)."""
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
