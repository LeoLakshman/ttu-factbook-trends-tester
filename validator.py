"""
Validation and Comparison Engine for TTU FactBook MC College.
Performs mathematical integrity checks, cross-page rollup validation,
change detection between Dev and Prod, and uncertainty flagging.
"""

from typing import Dict, Any, List, Optional, Tuple
from parser import parse_numeric


class Severity:
    CRITICAL = "CRITICAL"  # HTTP/Server crash, missing data grid
    HIGH = "HIGH"          # Math sum mismatch, rollup failure, dropped to zero
    MEDIUM = "MEDIUM"      # Dropped column, unexpected term change, missing department
    LOW = "LOW"            # Export button missing, label cosmetic difference
    INFO = "INFO"          # Intentional valid number changes / updates


def validate_row_sums(headers: List[str], row_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validate that horizontal breakdown numbers sum up to the reported Total column.
    Handles both flat tables and multi-tier tables with intermediate subtotals.
    """
    flags = []
    if not headers or "TOTAL" not in [h.upper() for h in headers]:
        return flags

    # Find the main Total column (typically the last column named TOTAL)
    total_idx = None
    for i in range(len(headers) - 1, -1, -1):
        if headers[i].upper() in ("TOTAL", "GRAND TOTAL"):
            total_idx = i
            break

    if total_idx is None:
        return flags

    total_col = headers[total_idx]
    reported_total = row_dict.get(f"{total_col}__num")
    if reported_total is None:
        return flags

    # Detect if intermediate subtotals exist (e.g. 'UG TOTAL', 'GR TOTAL', 'LW TOTAL', 'VS TOTAL')
    subtotal_cols = []
    base_cols = []
    for i in range(total_idx):
        h = headers[i]
        num_val = row_dict.get(f"{h}__num")
        if num_val is None:
            continue
        # Skip if column name indicates year/term or if the cell value looks like a 4-digit year (e.g. 2021-2026)
        if any(k in h.upper() for k in ("YEAR", "CODE", "TERM", "RANK", "LEVEL", "COHORT", "SEMESTER")):
            continue
        if i == 0 and 1950 <= num_val <= 2050:
            # First column is the Year label
            continue
        
        # Check if column is an intermediate subtotal
        if "TOTAL" in h.upper() or "SUBTOTAL" in h.upper():
            subtotal_cols.append(h)
        else:
            base_cols.append(h)

    # Case A: Table has intermediate subtotals (like ENRCOLLCLASS or ENRCOLLSEX)
    # Check if the sum of primary subtotals equals grand total
    if len(subtotal_cols) >= 2:
        # If columns like ['UG TOTAL', 'GR TOTAL', 'LW TOTAL', 'VS TOTAL'] exist:
        primary_subtotals = [c for c in subtotal_cols if not any(k in c.upper() for k in ("MALE", "FEMALE"))]
        if not primary_subtotals:
            primary_subtotals = subtotal_cols

        subtotal_sum = sum(row_dict.get(f"{c}__num", 0.0) for c in primary_subtotals)
        diff = round(subtotal_sum - reported_total, 2)
        if abs(diff) > 0.01:
            flags.append({
                "severity": Severity.HIGH,
                "type": "SUBTOTAL_SUM_MISMATCH",
                "message": (
                    f"Subtotals sum ({subtotal_sum:.0f}) does not match grand Total ({reported_total:.0f}). "
                    f"Difference: {diff:+.0f}. Evaluated subtotals: {', '.join(primary_subtotals)}"
                ),
                "breakdown_cols": primary_subtotals,
                "breakdown_sum": subtotal_sum,
                "reported_total": reported_total
            })

    # Case B: Standard flat table without intermediate subtotals
    elif len(base_cols) >= 2:
        breakdown_sum = sum(row_dict.get(f"{c}__num", 0.0) for c in base_cols)
        diff = round(breakdown_sum - reported_total, 2)
        if abs(diff) > 0.01:
            flags.append({
                "severity": Severity.HIGH,
                "type": "ROW_SUM_MISMATCH",
                "message": (
                    f"Row breakdown sum ({breakdown_sum:.0f}) does not match reported Total ({reported_total:.0f}). "
                    f"Difference: {diff:+.0f}. Evaluated columns: {', '.join(base_cols)}"
                ),
                "breakdown_cols": base_cols,
                "breakdown_sum": breakdown_sum,
                "reported_total": reported_total
            })

    return flags


def compare_pages(prod_data: Dict[str, Any], dev_data: Dict[str, Any], page_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare production snapshot with development snapshot for a specific subpage.
    """
    report = {
        "title": page_meta.get("title", prod_data.get("title", "Unknown Page")),
        "category": page_meta.get("category", "General"),
        "path": page_meta.get("path", ""),
        "prod_url": prod_data.get("url", ""),
        "dev_url": dev_data.get("url", ""),
        "status": "PASSED",  # PASSED, CHANGED, FLAGGED, ERROR
        "flags": [],
        "changes": [],
        "prod_summary": {},
        "dev_summary": {},
        "table_comparison": [],
        "functionality": {
            "prod_http": prod_data.get("status_code"),
            "dev_http": dev_data.get("status_code"),
            "dev_table_present": bool(dev_data.get("all_rows")),
            "dev_excel_export": dev_data.get("export_excel", False),
            "dev_pdf_export": dev_data.get("export_pdf", False),
            "dropdown_options_count": len(dev_data.get("dropdown_terms", []))
        }
    }

    # 1. HTTP and Server Error Checks
    dev_status = dev_data.get("status_code")
    dev_err = dev_data.get("error")
    if dev_status != 200 or dev_err:
        report["status"] = "ERROR"
        err_msg = dev_err if dev_err else f"HTTP {dev_status}"
        report["flags"].append({
            "severity": Severity.CRITICAL,
            "type": "DEV_SERVER_ERROR",
            "message": f"Dev page failed: {err_msg}"
        })
        return report

    if not dev_data.get("all_rows"):
        report["status"] = "ERROR"
        report["flags"].append({
            "severity": Severity.CRITICAL,
            "type": "EMPTY_DEV_GRID",
            "message": "Dev page rendered no table rows or data grid is missing."
        })
        return report

    # 2. Check MC presence
    prod_mc_rows = prod_data.get("mc_rows", [])
    dev_mc_rows = dev_data.get("mc_rows", [])

    if not dev_mc_rows and prod_mc_rows:
        report["status"] = "FLAGGED"
        report["flags"].append({
            "severity": Severity.HIGH,
            "type": "MC_MISSING_IN_DEV",
            "message": f"MC (College of Media & Communication) data found in Prod ({len(prod_mc_rows)} rows) but completely missing in Dev!"
        })

    # 3. Check Header differences
    prod_headers = prod_data.get("headers", [])
    dev_headers = dev_data.get("headers", [])
    if prod_headers != dev_headers:
        report["changes"].append({
            "type": "HEADER_CHANGE",
            "field": "Columns",
            "prod": prod_headers,
            "dev": dev_headers,
            "note": "Table column structure has been modified in development."
        })

    # 4. Math Integrity check on Dev MC rows
    for r in dev_mc_rows:
        row_flags = validate_row_sums(dev_headers, r)
        for rf in row_flags:
            row_label = " ".join(r.get("raw_cells", [])[:3])
            rf["message"] = f"[{row_label}] {rf['message']}"
            report["flags"].append(rf)
            if report["status"] != "ERROR":
                report["status"] = "FLAGGED"

    # 5. Row-by-Row MC Comparison
    # Build a lookup key for rows (e.g. dept code or program code)
    def get_row_key(r_cells):
        if len(r_cells) >= 3:
            return f"{r_cells[0]}|{r_cells[1]}|{r_cells[2]}"
        return "|".join(r_cells)

    prod_row_map = {get_row_key(r["raw_cells"]): r for r in prod_mc_rows}
    dev_row_map = {get_row_key(r["raw_cells"]): r for r in dev_mc_rows}

    # Find rows in Dev that weren't in Prod (new departments or programs)
    for dev_key, dev_row in dev_row_map.items():
        if dev_key not in prod_row_map:
            report["changes"].append({
                "type": "ADDED_ROW",
                "field": "MC Entity Added",
                "prod": None,
                "dev": " ".join(dev_row["raw_cells"][:4]),
                "note": f"New row detected in Dev: {' | '.join(dev_row['raw_cells'])}"
            })
            if report["status"] == "PASSED":
                report["status"] = "CHANGED"

    # Find rows in Prod that disappeared in Dev
    for prod_key, prod_row in prod_row_map.items():
        if prod_key not in dev_row_map:
            report["flags"].append({
                "severity": Severity.HIGH,
                "type": "REMOVED_ROW",
                "message": f"MC row present in Prod is missing in Dev: {' | '.join(prod_row['raw_cells'])}"
            })
            report["status"] = "FLAGGED"

    # Compare matching rows
    for key, prod_row in prod_row_map.items():
        if key in dev_row_map:
            dev_row = dev_row_map[key]
            row_label = " ".join(prod_row["raw_cells"][:3])
            
            # Compare each column
            for col in dev_headers:
                prod_num = prod_row.get(f"{col}__num")
                dev_num = dev_row.get(f"{col}__num")
                prod_raw = prod_row.get(col, "")
                dev_raw = dev_row.get(col, "")

                if prod_num is not None and dev_num is not None:
                    delta = dev_num - prod_num
                    if abs(delta) > 0.001:
                        pct_change = (delta / prod_num * 100) if prod_num > 0 else 0
                        change_item = {
                            "type": "NUMERIC_CHANGE",
                            "entity": row_label,
                            "metric": col,
                            "prod": prod_num,
                            "dev": dev_num,
                            "delta": delta,
                            "pct_change": round(pct_change, 1)
                        }
                        report["changes"].append(change_item)
                        if report["status"] == "PASSED":
                            report["status"] = "CHANGED"

                        # Flag unexpected drop to zero
                        if prod_num > 0 and dev_num == 0:
                            report["flags"].append({
                                "severity": Severity.HIGH,
                                "type": "UNEXPECTED_ZERO",
                                "message": f"[{row_label}] Metric '{col}' dropped from {prod_num:.0f} to 0 in Dev!"
                            })
                            report["status"] = "FLAGGED"

                elif prod_raw != dev_raw:
                    # String difference
                    report["changes"].append({
                        "type": "TEXT_CHANGE",
                        "entity": row_label,
                        "metric": col,
                        "prod": prod_raw,
                        "dev": dev_raw,
                        "note": f"Text modified: '{prod_raw}' -> '{dev_raw}'"
                    })
                    if report["status"] == "PASSED":
                        report["status"] = "CHANGED"

    # 6. Overall Totals Comparison
    prod_mc_total = prod_data.get("mc_total_row")
    dev_mc_total = dev_data.get("mc_total_row")

    if prod_mc_total:
        report["prod_summary"]["mc_total"] = prod_mc_total.get("raw_cells")
    if dev_mc_total:
        report["dev_summary"]["mc_total"] = dev_mc_total.get("raw_cells")

    # If any HIGH or CRITICAL flags exist, enforce FLAGGED status
    if any(f["severity"] in (Severity.HIGH, Severity.CRITICAL) for f in report["flags"]):
        report["status"] = "FLAGGED" if report["status"] != "ERROR" else "ERROR"

    return report


def validate_cross_page_rollups(page_results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate consistency between related pages (e.g. ENRCOLL vs ENRDEPT vs ENRCOLLDEPTPROG).
    """
    flags = []

    # Check Enrollment: College total vs Department total
    enr_coll = page_results.get("/FactBook/Enrollment/ENRCOLL.aspx")
    enr_dept = page_results.get("/FactBook/Enrollment/ENRDEPT.aspx")

    if enr_coll and enr_dept and enr_coll.get("dev_summary") and enr_dept.get("dev_summary"):
        coll_total = enr_coll["dev_summary"].get("mc_total")
        dept_total = enr_dept["dev_summary"].get("mc_total")
        if coll_total and dept_total:
            # Last cell is typically the Total count
            coll_val = parse_numeric(coll_total[-1])
            dept_val = parse_numeric(dept_total[-1])
            if coll_val is not None and dept_val is not None and coll_val != dept_val:
                flags.append({
                    "severity": Severity.HIGH,
                    "type": "CROSS_PAGE_ROLLUP_MISMATCH",
                    "pages": ["ENRCOLL.aspx", "ENRDEPT.aspx"],
                    "message": f"College total in ENRCOLL ({coll_val:.0f}) does not match Department rollup total in ENRDEPT ({dept_val:.0f})!"
                })

    return flags
