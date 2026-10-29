"""
Production FactBook Comprehensive Functionality & Faults Testing Suite.
Tests every page on production for:
1. Initial page load and table rendering
2. Export to Excel functionality (POST)
3. Export to PDF functionality (POST)
4. Foreign Campus exclusion checkbox (ForeignIndicator postback)
5. Bachelor's Degree-seeking checkbox (transferIndicator postback)
6. Math integrity (row sums & totals)
"""

import argparse
import concurrent.futures
import json
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import urllib3
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import PROD_BASE_URL, KEY_MC_PAGES, load_all_subpages
from parser import parse_numeric, is_mc_row
from validator import validate_row_sums

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
console = Console()


def test_single_page_functionality(page_meta: Dict[str, Any], timeout: int = 25) -> Dict[str, Any]:
    """
    Execute full functional test suite on a single production FactBook page.
    """
    path = page_meta["path"].strip()
    clean_path = path if path.startswith("/") else f"/{path}"
    url = f"{PROD_BASE_URL}{clean_path}"

    result: Dict[str, Any] = {
        "title": page_meta.get("title", clean_path),
        "category": page_meta.get("category", "General"),
        "path": clean_path,
        "url": url,
        "status": "HEALTHY",  # HEALTHY, FAULT, CRITICAL
        "faults": [],
        "tests": {
            "page_load": {"status": "UNKNOWN", "time_sec": 0, "http": 0},
            "grid_render": {"status": "UNKNOWN", "row_count": 0, "mc_found": False},
            "excel_export": {"status": "N/A", "mime": None, "size_bytes": 0, "filename": None},
            "pdf_export": {"status": "N/A", "mime": None, "size_bytes": 0, "filename": None},
            "foreign_campus": {"status": "N/A", "delta": None},
            "bachelor_degree": {"status": "N/A", "delta": None},
            "math_integrity": {"status": "UNKNOWN", "errors": 0}
        }
    }

    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # =========================================================================
    # TEST 1: Initial Page Load (GET)
    # =========================================================================
    t0 = time.time()
    try:
        r_get = s.get(url, timeout=timeout)
        load_time = round(time.time() - t0, 2)
        result["tests"]["page_load"]["http"] = r_get.status_code
        result["tests"]["page_load"]["time_sec"] = load_time

        if r_get.status_code != 200:
            result["status"] = "CRITICAL"
            result["tests"]["page_load"]["status"] = "FAIL"
            result["faults"].append({
                "severity": "CRITICAL",
                "component": "PAGE_LOAD",
                "message": f"HTTP {r_get.status_code} returned on page load."
            })
            return result

        if "Server Error in '/' Application" in r_get.text or "Runtime Error" in r_get.text:
            result["status"] = "CRITICAL"
            result["tests"]["page_load"]["status"] = "FAIL"
            result["faults"].append({
                "severity": "CRITICAL",
                "component": "SERVER_ERROR",
                "message": "ASP.NET unhandled runtime exception encountered."
            })
            return result

        result["tests"]["page_load"]["status"] = "PASS"

    except Exception as e:
        result["status"] = "CRITICAL"
        result["tests"]["page_load"]["status"] = "FAIL"
        result["faults"].append({
            "severity": "CRITICAL",
            "component": "PAGE_LOAD",
            "message": f"Connection timeout or network failure: {e}"
        })
        return result

    soup = BeautifulSoup(r_get.text, "lxml")

    # Extract ViewState and Form Data
    vs_tag = soup.find("input", {"id": "__VIEWSTATE"})
    vsg_tag = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
    ev_tag = soup.find("input", {"id": "__EVENTVALIDATION"})

    viewstate = vs_tag["value"] if vs_tag else None
    viewstate_gen = vsg_tag["value"] if vsg_tag else None
    event_validation = ev_tag["value"] if ev_tag else None

    # =========================================================================
    # TEST 2: Data Grid Rendering & Math Verification
    # =========================================================================
    grid = soup.find("table", id=re.compile(r"(MyGridView|GridView|grid)", re.IGNORECASE))
    if not grid:
        tables = soup.find_all("table")
        if tables:
            grid = max(tables, key=lambda t: len(t.find_all("tr")))

    if not grid:
        result["status"] = "CRITICAL"
        result["tests"]["grid_render"]["status"] = "FAIL"
        result["faults"].append({
            "severity": "CRITICAL",
            "component": "GRID_RENDER",
            "message": "No data table grid was rendered on the page."
        })
    else:
        rows = grid.find_all("tr")
        result["tests"]["grid_render"]["row_count"] = len(rows)
        if len(rows) <= 1:
            result["status"] = "FAULT"
            result["tests"]["grid_render"]["status"] = "EMPTY"
            result["faults"].append({
                "severity": "HIGH",
                "component": "GRID_RENDER",
                "message": "Data table is empty (0 data rows)."
            })
        else:
            result["tests"]["grid_render"]["status"] = "PASS"

            # Check headers and math
            headers = []
            header_row = [tr for tr in rows if tr.find("th")]
            if header_row:
                headers = [td.get_text(strip=True) for td in header_row[-1].find_all(["th", "td"])]
            else:
                headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]

            math_errors = 0
            mc_present = False
            for tr in rows[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                if not cells:
                    continue
                if is_mc_row(cells):
                    mc_present = True

                row_dict = {}
                for idx, c in enumerate(cells):
                    col_name = headers[idx] if idx < len(headers) else f"COL_{idx}"
                    num = parse_numeric(c)
                    if num is not None:
                        row_dict[f"{col_name}__num"] = num

                flags = validate_row_sums(headers, row_dict)
                if flags:
                    math_errors += 1
                    for fl in flags:
                        result["faults"].append({
                            "severity": "HIGH",
                            "component": "MATH_INTEGRITY",
                            "message": f"[{' '.join(cells[:3])}] {fl['message']}"
                        })

            result["tests"]["grid_render"]["mc_found"] = mc_present
            result["tests"]["math_integrity"]["errors"] = math_errors
            result["tests"]["math_integrity"]["status"] = "PASS" if math_errors == 0 else "FAIL"
            if math_errors > 0 and result["status"] == "HEALTHY":
                result["status"] = "FAULT"

    # If ViewState is missing, cannot perform POST tests
    if not viewstate:
        result["faults"].append({
            "severity": "MEDIUM",
            "component": "POSTBACK",
            "message": "Missing __VIEWSTATE; interactive export and checkbox tests skipped."
        })
        return result

    # Get active dropdown value if exists
    dropdown = soup.find("select", id=re.compile(r"(DropDownList|Term|Year)", re.IGNORECASE))
    dropdown_name = dropdown.get("name") if dropdown else None
    dropdown_val = dropdown.find("option", {"selected": True}) if dropdown else None
    selected_term_val = dropdown_val.get("value") if dropdown_val else None

    # Base form data helper
    def get_base_payload():
        p = {"__VIEWSTATE": viewstate}
        if viewstate_gen:
            p["__VIEWSTATEGENERATOR"] = viewstate_gen
        if event_validation:
            p["__EVENTVALIDATION"] = event_validation
        if dropdown_name and selected_term_val:
            p[dropdown_name] = selected_term_val
        return p

    # =========================================================================
    # TEST 3: Export to Excel (POST)
    # =========================================================================
    excel_btn = soup.find("input", id=re.compile(r"expToExcel", re.IGNORECASE))
    if excel_btn:
        btn_name = excel_btn.get("name", "expToExcel")
        payload = get_base_payload()
        payload[f"{btn_name}.x"] = "15"
        payload[f"{btn_name}.y"] = "15"

        try:
            r_ex = s.post(url, data=payload, timeout=timeout)
            ctype = r_ex.headers.get("Content-Type", "")
            cdisp = r_ex.headers.get("Content-Disposition", "")
            size = len(r_ex.content)

            result["tests"]["excel_export"]["mime"] = ctype
            result["tests"]["excel_export"]["size_bytes"] = size
            result["tests"]["excel_export"]["filename"] = cdisp

            # Valid Excel response check
            is_valid_excel = (
                r_ex.status_code == 200 and
                size > 800 and
                ("openxmlformats" in ctype or "vnd.ms-excel" in ctype or r_ex.content.startswith(b"PK\x03\x04") or b"<html" in r_ex.content[:100])
            )

            if is_valid_excel:
                result["tests"]["excel_export"]["status"] = "PASS"
            else:
                result["tests"]["excel_export"]["status"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "CRITICAL",
                    "component": "EXCEL_EXPORT",
                    "message": f"Excel export failed (HTTP {r_ex.status_code}, Size: {size} bytes, Type: '{ctype}')."
                })
        except Exception as e:
            result["tests"]["excel_export"]["status"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "CRITICAL",
                "component": "EXCEL_EXPORT",
                "message": f"Excel export POST request threw exception: {e}"
            })

    # =========================================================================
    # TEST 4: Export to PDF (POST)
    # =========================================================================
    pdf_btn = soup.find("input", id=re.compile(r"(expToWord|pdf)", re.IGNORECASE))
    if pdf_btn:
        btn_name = pdf_btn.get("name", "expToWord")
        payload = get_base_payload()
        payload[f"{btn_name}.x"] = "15"
        payload[f"{btn_name}.y"] = "15"

        try:
            r_pdf = s.post(url, data=payload, timeout=timeout)
            ctype = r_pdf.headers.get("Content-Type", "")
            cdisp = r_pdf.headers.get("Content-Disposition", "")
            size = len(r_pdf.content)

            result["tests"]["pdf_export"]["mime"] = ctype
            result["tests"]["pdf_export"]["size_bytes"] = size
            result["tests"]["pdf_export"]["filename"] = cdisp

            # Valid PDF response check
            is_valid_pdf = (
                r_pdf.status_code == 200 and
                size > 500 and
                ("application/pdf" in ctype or r_pdf.content.startswith(b"%PDF-"))
            )

            if is_valid_pdf:
                result["tests"]["pdf_export"]["status"] = "PASS"
            else:
                result["tests"]["pdf_export"]["status"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "CRITICAL",
                    "component": "PDF_EXPORT",
                    "message": f"PDF export failed (HTTP {r_pdf.status_code}, Size: {size} bytes, Type: '{ctype}')."
                })
        except Exception as e:
            result["tests"]["pdf_export"]["status"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "CRITICAL",
                "component": "PDF_EXPORT",
                "message": f"PDF export POST request threw exception: {e}"
            })

    # =========================================================================
    # TEST 5: Foreign Campus Exclusion Checkbox (ForeignIndicator)
    # =========================================================================
    foreign_cb = soup.find("input", id=re.compile(r"ForeignIndicator", re.IGNORECASE))
    if foreign_cb:
        cb_name = foreign_cb.get("name", "ForeignIndicator")
        payload = get_base_payload()
        # Toggle: if default was unchecked, send "on" with __EVENTTARGET
        is_default_checked = foreign_cb.get("checked") is not None
        if not is_default_checked:
            payload[cb_name] = "on"
        payload["__EVENTTARGET"] = cb_name
        payload["__EVENTARGUMENT"] = ""

        try:
            r_fc = s.post(url, data=payload, timeout=timeout)
            if r_fc.status_code == 200 and "Server Error" not in r_fc.text:
                soup_fc = BeautifulSoup(r_fc.text, "lxml")
                grid_fc = soup_fc.find("table", id=re.compile(r"(MyGridView|GridView|grid)", re.IGNORECASE))
                if grid_fc and len(grid_fc.find_all("tr")) > 1:
                    result["tests"]["foreign_campus"]["status"] = "PASS"
                else:
                    result["tests"]["foreign_campus"]["status"] = "FAIL"
                    if result["status"] == "HEALTHY":
                        result["status"] = "FAULT"
                    result["faults"].append({
                        "severity": "HIGH",
                        "component": "FOREIGN_CAMPUS_CHECKBOX",
                        "message": "Data table vanished or emptied when Foreign Campus checkbox was toggled."
                    })
            else:
                result["tests"]["foreign_campus"]["status"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "FOREIGN_CAMPUS_CHECKBOX",
                    "message": f"Foreign Campus toggle returned HTTP {r_fc.status_code} or server error."
                })
        except Exception as e:
            result["tests"]["foreign_campus"]["status"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "HIGH",
                "component": "FOREIGN_CAMPUS_CHECKBOX",
                "message": f"Foreign Campus checkbox postback failed: {e}"
            })

    # =========================================================================
    # TEST 6: Bachelor's Degree-Seeking Checkbox (transferIndicator)
    # =========================================================================
    bachelor_cb = soup.find("input", id=re.compile(r"transferIndicator", re.IGNORECASE))
    if bachelor_cb:
        cb_name = bachelor_cb.get("name", "transferIndicator")
        payload = get_base_payload()
        is_default_checked = bachelor_cb.get("checked") is not None
        if not is_default_checked:
            payload[cb_name] = "on"
        # preserve foreign indicator if present
        if foreign_cb:
            payload["ForeignIndicator"] = "on"
        payload["__EVENTTARGET"] = cb_name
        payload["__EVENTARGUMENT"] = ""

        try:
            r_ti = s.post(url, data=payload, timeout=timeout)
            if r_ti.status_code == 200 and "Server Error" not in r_ti.text:
                soup_ti = BeautifulSoup(r_ti.text, "lxml")
                grid_ti = soup_ti.find("table", id=re.compile(r"(MyGridView|GridView|grid)", re.IGNORECASE))
                if grid_ti and len(grid_ti.find_all("tr")) > 1:
                    result["tests"]["bachelor_degree"]["status"] = "PASS"
                else:
                    result["tests"]["bachelor_degree"]["status"] = "FAIL"
                    if result["status"] == "HEALTHY":
                        result["status"] = "FAULT"
                    result["faults"].append({
                        "severity": "HIGH",
                        "component": "BACHELOR_DEGREE_CHECKBOX",
                        "message": "Data table vanished or emptied when Bachelor's Degree checkbox was toggled."
                    })
            else:
                result["tests"]["bachelor_degree"]["status"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "BACHELOR_DEGREE_CHECKBOX",
                    "message": f"Bachelor's Degree checkbox toggle returned HTTP {r_ti.status_code} or server error."
                })
        except Exception as e:
            result["tests"]["bachelor_degree"]["status"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "HIGH",
                "component": "BACHELOR_DEGREE_CHECKBOX",
                "message": f"Bachelor's Degree checkbox postback failed: {e}"
            })

    return result


def generate_prod_faults_html_report(results: List[Dict[str, Any]], output_path: Path) -> str:
    """Generate interactive production functionality & faults HTML dashboard."""
    total_pages = len(results)
    healthy_pages = sum(1 for r in results if r["status"] == "HEALTHY")
    fault_pages = sum(1 for r in results if r["status"] == "FAULT")
    critical_pages = sum(1 for r in results if r["status"] == "CRITICAL")

    # Metrics
    excel_tests = [r["tests"]["excel_export"]["status"] for r in results if r["tests"]["excel_export"]["status"] != "N/A"]
    excel_passed = excel_tests.count("PASS")
    excel_total = len(excel_tests)

    pdf_tests = [r["tests"]["pdf_export"]["status"] for r in results if r["tests"]["pdf_export"]["status"] != "N/A"]
    pdf_passed = pdf_tests.count("PASS")
    pdf_total = len(pdf_tests)

    foreign_tests = [r["tests"]["foreign_campus"]["status"] for r in results if r["tests"]["foreign_campus"]["status"] != "N/A"]
    foreign_passed = foreign_tests.count("PASS")
    foreign_total = len(foreign_tests)

    bachelor_tests = [r["tests"]["bachelor_degree"]["status"] for r in results if r["tests"]["bachelor_degree"]["status"] != "N/A"]
    bachelor_passed = bachelor_tests.count("PASS")
    bachelor_total = len(bachelor_tests)

    math_tests = [r["tests"]["math_integrity"]["status"] for r in results if r["tests"]["math_integrity"]["status"] != "UNKNOWN"]
    math_passed = math_tests.count("PASS")
    math_total = len(math_tests)

    results_json = json.dumps(results, indent=2)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TTU FactBook Production Functionality & Faults Audit</title>
    <style>
        :root {{
            --ttu-red: #CC0000;
            --ttu-black: #111111;
            --bg-color: #f4f6f9;
            --card-bg: #ffffff;
            --text-main: #2b2f38;
            --text-muted: #6c757d;
            --border-color: #e2e8f0;
            --pass-color: #10b981;
            --warn-color: #f59e0b;
            --danger-color: #ef4444;
            --info-color: #3b82f6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            line-height: 1.5;
            padding: 24px;
        }}
        .header {{
            background: linear-gradient(135deg, #111111 0%, #300000 100%);
            color: white;
            padding: 28px 32px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.15);
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 6px solid var(--ttu-red);
        }}
        .header h1 {{ font-size: 24px; font-weight: 700; }}
        .header .subtitle {{ color: #d1d5db; font-size: 14px; margin-top: 6px; }}
        .header-meta {{ text-align: right; font-size: 13px; color: #9ca3af; }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--card-bg);
            padding: 18px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        }}
        .kpi-card .kpi-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.05em;
        }}
        .kpi-card .kpi-value {{
            font-size: 28px;
            font-weight: 700;
            margin-top: 6px;
        }}
        .kpi-card.pass .kpi-value {{ color: var(--pass-color); }}
        .kpi-card.fault .kpi-value {{ color: var(--warn-color); }}
        .kpi-card.crit .kpi-value {{ color: var(--danger-color); }}

        .control-bar {{
            background: var(--card-bg);
            padding: 16px 20px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .filter-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .btn {{
            border: 1px solid var(--border-color);
            background: white;
            color: var(--text-main);
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn:hover {{ background: #f1f5f9; }}
        .btn.active {{
            background: var(--ttu-red);
            color: white;
            border-color: var(--ttu-red);
        }}
        .search-box input {{
            padding: 8px 14px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 13px;
            width: 280px;
        }}

        /* Table */
        .table-card {{
            background: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
        }}
        table.matrix {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        table.matrix th, table.matrix td {{
            padding: 12px 14px;
            border-bottom: 1px solid var(--border-color);
        }}
        table.matrix th {{
            background: #f8fafc;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
        }}
        table.matrix tr:hover {{ background: #fafbfc; }}

        .badge-status {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .badge-status.PASS {{ background: #ecfdf5; color: #047857; }}
        .badge-status.FAIL {{ background: #fef2f2; color: #b91c1c; font-weight: bold; }}
        .badge-status.NA {{ background: #f1f5f9; color: #94a3b8; }}

        .overall-pill {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .overall-pill.HEALTHY {{ background: #ecfdf5; color: #047857; }}
        .overall-pill.FAULT {{ background: #fffbeb; color: #b45309; }}
        .overall-pill.CRITICAL {{ background: #fef2f2; color: #b91c1c; }}

        .fault-desc {{
            color: #b91c1c;
            font-size: 12px;
            margin-top: 4px;
            font-weight: 500;
        }}
        a.page-link {{
            color: var(--ttu-red);
            text-decoration: none;
            font-weight: 600;
        }}
        a.page-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>Texas Tech University - FactBook Production Testing</h1>
            <div class="subtitle">Faults & Functionality Audit: Page Loads, Export to Excel/PDF, Foreign Campus & Bachelor's Checkboxes, Math Integrity</div>
        </div>
        <div class="header-meta">
            <div><strong>Environment:</strong> PRODUCTION (techdata.irs.ttu.edu)</div>
            <div><strong>Timestamp:</strong> {timestamp}</div>
        </div>
    </div>

    <!-- KPIs -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Pages Tested</div>
            <div class="kpi-value">{total_pages}</div>
        </div>
        <div class="kpi-card pass">
            <div class="kpi-label">100% Healthy Pages</div>
            <div class="kpi-value">{healthy_pages}</div>
        </div>
        <div class="kpi-card fault">
            <div class="kpi-label">Pages with Faults</div>
            <div class="kpi-value">{fault_pages}</div>
        </div>
        <div class="kpi-card crit">
            <div class="kpi-label">Critical / Server Crashes</div>
            <div class="kpi-value">{critical_pages}</div>
        </div>
        <div class="kpi-card pass">
            <div class="kpi-label">Excel Export Success</div>
            <div class="kpi-value">{excel_passed}/{excel_total}</div>
        </div>
        <div class="kpi-card pass">
            <div class="kpi-label">PDF Export Success</div>
            <div class="kpi-value">{pdf_passed}/{pdf_total}</div>
        </div>
        <div class="kpi-card pass">
            <div class="kpi-label">Foreign Campus Box</div>
            <div class="kpi-value">{foreign_passed}/{foreign_total}</div>
        </div>
        <div class="kpi-card pass">
            <div class="kpi-label">Bachelor's Degree Box</div>
            <div class="kpi-value">{bachelor_passed}/{bachelor_total}</div>
        </div>
    </div>

    <!-- Control Bar -->
    <div class="control-bar">
        <div class="filter-buttons">
            <button class="btn active" onclick="setFilter('ALL')">All Pages ({total_pages})</button>
            <button class="btn" onclick="setFilter('FAULT')">🚨 Faults ({fault_pages + critical_pages})</button>
            <button class="btn" onclick="setFilter('HEALTHY')">✅ Healthy ({healthy_pages})</button>
            <button class="btn" onclick="setFilter('EXCEL_FAIL')">Excel Fails</button>
            <button class="btn" onclick="setFilter('PDF_FAIL')">PDF Fails</button>
            <button class="btn" onclick="setFilter('CB_FAIL')">Checkbox Fails</button>
        </div>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search page name, category, or path..." onkeyup="renderTable()">
        </div>
    </div>

    <!-- Results Table -->
    <div class="table-card">
        <table class="matrix" id="matrixTable">
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Subpage Title</th>
                    <th>Status</th>
                    <th>Page Load (GET)</th>
                    <th>Data Grid</th>
                    <th>Export Excel</th>
                    <th>Export PDF</th>
                    <th>Foreign Campus</th>
                    <th>Bachelor Degree</th>
                    <th>Math Integrity</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>

    <script>
        const results = {results_json};
        let currentFilter = 'ALL';

        function badge(status) {{
            if (status === 'PASS') return `<span class="badge-status PASS">PASS</span>`;
            if (status === 'FAIL') return `<span class="badge-status FAIL">FAIL</span>`;
            return `<span class="badge-status NA">N/A</span>`;
        }}

        function renderTable() {{
            const tbody = document.getElementById('tableBody');
            const search = document.getElementById('searchInput').value.toLowerCase();
            tbody.innerHTML = '';

            results.forEach(r => {{
                // Filter logic
                if (currentFilter === 'FAULT' && r.status === 'HEALTHY') return;
                if (currentFilter === 'HEALTHY' && r.status !== 'HEALTHY') return;
                if (currentFilter === 'EXCEL_FAIL' && r.tests.excel_export.status !== 'FAIL') return;
                if (currentFilter === 'PDF_FAIL' && r.tests.pdf_export.status !== 'FAIL') return;
                if (currentFilter === 'CB_FAIL' && r.tests.foreign_campus.status !== 'FAIL' && r.tests.bachelor_degree.status !== 'FAIL') return;

                const textToSearch = `${{r.category}} ${{r.title}} ${{r.path}} ${{JSON.stringify(r.faults || [])}}`.toLowerCase();
                if (search && !textToSearch.includes(search)) return;

                const tr = document.createElement('tr');
                let faultsHtml = '';
                if (r.faults && r.faults.length > 0) {{
                    faultsHtml = r.faults.map(f => `<div class="fault-desc">⚠️ [${{f.component}}] ${{f.message}}</div>`).join('');
                }}

                tr.innerHTML = `
                    <td><span style="font-weight:600; color:var(--text-muted); font-size:11px;">${{r.category}}</span></td>
                    <td>
                        <a class="page-link" href="${{r.url}}" target="_blank">${{r.title}}</a>
                        <div style="font-size:11px; color:var(--text-muted);">${{r.path}}</div>
                        ${{faultsHtml}}
                    </td>
                    <td><span class="overall-pill ${{r.status}}">${{r.status}}</span></td>
                    <td>${{r.tests.page_load.status === 'PASS' ? `<span class="badge-status PASS">${{r.tests.page_load.time_sec}}s</span>` : `<span class="badge-status FAIL">HTTP ${{r.tests.page_load.http}}</span>`}}</td>
                    <td>${{r.tests.grid_render.status === 'PASS' ? `<span class="badge-status PASS">${{r.tests.grid_render.row_count}} rows</span>` : badge(r.tests.grid_render.status)}}</td>
                    <td>${{badge(r.tests.excel_export.status)}}</td>
                    <td>${{badge(r.tests.pdf_export.status)}}</td>
                    <td>${{badge(r.tests.foreign_campus.status)}}</td>
                    <td>${{badge(r.tests.bachelor_degree.status)}}</td>
                    <td>${{badge(r.tests.math_integrity.status)}}</td>
                `;
                tbody.appendChild(tr);
            }});

            if (tbody.children.length === 0) {{
                tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:32px; color:var(--text-muted);">No pages found matching filter.</td></tr>`;
            }}
        }}

        function setFilter(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.filter-buttons .btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            renderTable();
        }}

        renderTable();
    </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="TTU FactBook Production Functionality & Faults Test Suite")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent worker threads (default: 6)")
    parser.add_argument("--quick", action="store_true", help="Test 27 priority subpages")
    parser.add_argument("--all", action="store_true", help="Test all 155 FactBook subpages")
    parser.add_argument("--category", help="Filter subpages by category (e.g. Enrollment, Degree, Graduation)")
    parser.add_argument("--pages", help="Comma separated paths or keywords to test (e.g. GRADCOLL,ENRCOLL)")
    parser.add_argument("--output-dir", default="./reports", help="Output directory for reports")

    args = parser.parse_args()

    if args.all:
        subpages = load_all_subpages()
    elif args.quick or (not args.category and not args.pages):
        subpages = KEY_MC_PAGES
    else:
        subpages = load_all_subpages()

    if args.category:
        cat_lower = args.category.lower()
        subpages = [p for p in subpages if cat_lower in p.get("category", "").lower()]

    if args.pages:
        targets = [t.strip().lower() for t in args.pages.split(",")]
        subpages = [p for p in subpages if any(t in p.get("path", "").lower() or t in p.get("title", "").lower() for t in targets)]

    console.print(Panel(
        f"[bold cyan]TTU FactBook Production Comprehensive Faults & Functionality Testing[/bold cyan]\n"
        f"Testing [bold]{len(subpages)}[/bold] production pages with [bold]{args.workers}[/bold] concurrent workers.\n"
        f"• Page Load & Data Grid\n"
        f"• Export to Excel (POST)\n"
        f"• Export to PDF (POST)\n"
        f"• Exclude Foreign Campus Checkbox\n"
        f"• Bachelor's Degree-Seeking Checkbox\n"
        f"• Horizontal & Vertical Math Integrity",
        border_style="red"
    ))

    t_start = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_page = {executor.submit(test_single_page_functionality, p): p for p in subpages}
        completed = 0
        for future in concurrent.futures.as_completed(future_to_page):
            completed += 1
            res = future.result()
            results.append(res)
            status_color = "green" if res["status"] == "HEALTHY" else ("yellow" if res["status"] == "FAULT" else "red")
            console.print(f"[{completed}/{len(subpages)}] [{status_color}]{res['status']}[/{status_color}] {res['title']} ({res['path']})")

    elapsed = round(time.time() - t_start, 2)
    output_dir = Path(args.output_dir)
    html_file = output_dir / "prod_faults_dashboard.html"
    json_file = output_dir / "prod_faults_data.json"

    generate_prod_faults_html_report(results, html_file)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Print summary
    healthy = sum(1 for r in results if r["status"] == "HEALTHY")
    faults = sum(1 for r in results if r["status"] == "FAULT")
    critical = sum(1 for r in results if r["status"] == "CRITICAL")

    console.print(Panel(
        f"[bold]Total Pages Tested:[/bold] {len(results)} in {elapsed}s\n"
        f"[bold green]✓ 100% Healthy Pages:[/bold green] {healthy}\n"
        f"[bold yellow]⚠️ Pages with Faults:[/bold yellow] {faults}\n"
        f"[bold red]❌ Critical Pages:[/bold red] {critical}\n\n"
        f"[bold underline]Interactive Production Faults Dashboard Saved to:[/bold underline]\n"
        f"[bold cyan]{html_file.resolve()}[/bold cyan]",
        title="[bold]Production Audit Complete[/bold]",
        border_style="green" if faults == 0 and critical == 0 else "yellow"
    ))


if __name__ == "__main__":
    main()
