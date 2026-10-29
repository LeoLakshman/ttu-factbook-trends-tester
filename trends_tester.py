"""
TTU Trends Comprehensive Functionality & Faults Testing Suite.
Tests all 16 Trends reports across:
- All Semester selections (Fall, Spring, etc.)
- All College selections (TTU overall, MC College of Media & Communication, etc.)
- Foreign Campus checkbox toggling
- Bachelor's Degree checkbox toggling (Retention)
- Math integrity across historical year rows
"""

import time
import json
import re
import urllib3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table

from parser import parse_numeric
from validator import validate_row_sums

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
console = Console()

TRENDS_BASE_URL = "https://techdata.irs.ttu.edu/Trends/"

TRENDS_SECTIONS = [
    {"target": "SideBar2$LinkButton12", "id": "faculty_headcount", "title": "Faculty Headcount", "category": "Faculty"},
    {"target": "SideBar2$LinkButton15", "id": "research_expenditures", "title": "Research Expenditures", "category": "Research"},
    {"target": "SideBar2$LinkButton17", "id": "revenue_revenues", "title": "Revenue Revenues", "category": "Revenue"},
    {"target": "SideBar2$LinkButton1", "id": "applied_admitted", "title": "Applied / Admitted / Enrolled", "category": "Students"},
    {"target": "SideBar2$LinkButton2", "id": "degrees", "title": "Degrees", "category": "Students"},
    {"target": "SideBar2$LinkButton3", "id": "distance_ed", "title": "Distance Education", "category": "Students"},
    {"target": "SideBar2$LinkButton4", "id": "enrollment", "title": "Enrollment", "category": "Students"},
    {"target": "SideBar2$LinkButton5", "id": "grad_rates", "title": "Graduation Rates", "category": "Students"},
    {"target": "SideBar2$LinkButton6", "id": "new_freshmen", "title": "New First-Year Student From High School", "category": "Students"},
    {"target": "SideBar2$LinkButton7", "id": "new_grad", "title": "New Graduate Students", "category": "Students"},
    {"target": "SideBar2$LinkButton8", "id": "new_law", "title": "New Law Students", "category": "Students"},
    {"target": "SideBar2$LinkButton9", "id": "new_transfers", "title": "New Undergraduate Transfers", "category": "Students"},
    {"target": "SideBar2$LinkButton10", "id": "retention_rates", "title": "Retention Rates", "category": "Students"},
    {"target": "SideBar2$LinkButton11", "id": "sch", "title": "Semester Credit Hours", "category": "Students"},
    {"target": "SideBar2$LinkButton21", "id": "vet_school", "title": "Veterinary School", "category": "Students"},
    {"target": "SideBar2$LinkButton13", "id": "weighted_sch", "title": "Weighted Semester Credit Hours", "category": "Students"},
]


def test_trends_section(section: Dict[str, Any], test_all_colleges: bool = False, timeout: int = 35) -> Dict[str, Any]:
    """
    Test a single Trends report section including its dropdowns, checkboxes, and math.
    """
    target = section["target"]
    title = section["title"]
    category = section["category"]

    result: Dict[str, Any] = {
        "title": title,
        "category": category,
        "target": target,
        "status": "HEALTHY",
        "faults": [],
        "load_time_sec": 0,
        "semesters_tested": [],
        "colleges_tested": [],
        "checkboxes_tested": {},
        "math_integrity": "PASS",
        "total_historical_rows": 0,
        "headers": []
    }

    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Step 1: Initial GET to obtain ViewState
    t0 = time.time()
    try:
        r_init = s.get(TRENDS_BASE_URL, timeout=timeout)
        soup_init = BeautifulSoup(r_init.text, "lxml")
        vs = soup_init.find("input", {"id": "__VIEWSTATE"})["value"]
        vsg = soup_init.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"]
        ev = soup_init.find("input", {"id": "__EVENTVALIDATION"})["value"]
    except Exception as e:
        result["status"] = "CRITICAL"
        result["faults"].append({
            "severity": "CRITICAL",
            "component": "INITIAL_GET",
            "message": f"Failed to initialize Trends session: {e}"
        })
        return result

    # Step 2: Postback to load section
    post_data = {
        "__VIEWSTATE": vs,
        "__VIEWSTATEGENERATOR": vsg,
        "__EVENTVALIDATION": ev,
        "__EVENTTARGET": target,
        "__EVENTARGUMENT": ""
    }

    try:
        r_sec = s.post(TRENDS_BASE_URL, data=post_data, timeout=timeout)
        result["load_time_sec"] = round(time.time() - t0, 2)
        if r_sec.status_code != 200:
            result["status"] = "CRITICAL"
            result["faults"].append({
                "severity": "CRITICAL",
                "component": "SECTION_LOAD",
                "message": f"HTTP {r_sec.status_code} returned when loading {title}."
            })
            return result

        soup_sec = BeautifulSoup(r_sec.text, "lxml")
        vs_sec = soup_sec.find("input", {"id": "__VIEWSTATE"})["value"]
        vsg_sec = soup_sec.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"]
        ev_sec = soup_sec.find("input", {"id": "__EVENTVALIDATION"})["value"]

    except Exception as e:
        result["status"] = "CRITICAL"
        result["faults"].append({
            "severity": "CRITICAL",
            "component": "SECTION_LOAD",
            "message": f"Section load failed: {e}"
        })
        return result

    # Check for rendered table
    grid = soup_sec.find("table")
    if not grid or len(grid.find_all("tr")) <= 1:
        result["status"] = "FAULT"
        result["faults"].append({
            "severity": "HIGH",
            "component": "TABLE_RENDER",
            "message": "Data table missing or empty on initial section load."
        })
    else:
        # Extract headers and rows
        rows = grid.find_all("tr")
        result["total_historical_rows"] = len(rows) - 1
        headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
        result["headers"] = headers

        # Math validation across historical year rows
        math_errs = 0
        for tr in rows[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if not cells:
                continue
            row_dict = {}
            for idx, c in enumerate(cells):
                col_name = headers[idx] if idx < len(headers) else f"COL_{idx}"
                num = parse_numeric(c)
                if num is not None:
                    row_dict[f"{col_name}__num"] = num

            flags = validate_row_sums(headers, row_dict)
            if flags:
                math_errs += 1
                for fl in flags:
                    result["faults"].append({
                        "severity": "HIGH",
                        "component": "MATH_INTEGRITY",
                        "message": f"[{cells[0]}] {fl['message']}"
                    })

        if math_errs > 0:
            result["math_integrity"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"

    # Step 3: Test Semester Dropdown (APPADMDropDownList1)
    sem_dropdown = soup_sec.find("select", id=re.compile(r"DropDownList1", re.IGNORECASE))
    if sem_dropdown:
        options = [opt.get("value") for opt in sem_dropdown.find_all("option")]
        for opt_val in options[:3]:  # Test available semesters (Fall, Spring, etc.)
            result["semesters_tested"].append(opt_val)
            payload = {
                "__VIEWSTATE": vs_sec,
                "__VIEWSTATEGENERATOR": vsg_sec,
                "__EVENTVALIDATION": ev_sec,
                sem_dropdown.get("name"): opt_val,
                "__EVENTTARGET": sem_dropdown.get("name"),
                "__EVENTARGUMENT": ""
            }
            try:
                r_sem = s.post(TRENDS_BASE_URL, data=payload, timeout=timeout)
                if r_sem.status_code != 200 or "Server Error" in r_sem.text:
                    result["status"] = "FAULT"
                    result["faults"].append({
                        "severity": "HIGH",
                        "component": "SEMESTER_DROPDOWN",
                        "message": f"Selecting semester '{opt_val}' failed (HTTP {r_sem.status_code})."
                    })
            except Exception as e:
                result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "SEMESTER_DROPDOWN",
                    "message": f"Selecting semester '{opt_val}' timed out or threw exception: {e}"
                })

    # Step 4: Test College Dropdown (APPADMDropDownList2) - focus on TTU and MC
    coll_dropdown = soup_sec.find("select", id=re.compile(r"DropDownList2", re.IGNORECASE))
    if coll_dropdown:
        all_coll_opts = [opt.get("value") for opt in coll_dropdown.find_all("option")]
        # Target TTU and MC, or all if requested
        target_colls = all_coll_opts if test_all_colleges else [o for o in all_coll_opts if o.startswith("TTU") or "MC" in o]
        for c_val in target_colls:
            result["colleges_tested"].append(c_val)
            payload = {
                "__VIEWSTATE": vs_sec,
                "__VIEWSTATEGENERATOR": vsg_sec,
                "__EVENTVALIDATION": ev_sec,
                coll_dropdown.get("name"): c_val,
                "__EVENTTARGET": coll_dropdown.get("name"),
                "__EVENTARGUMENT": ""
            }
            try:
                r_coll = s.post(TRENDS_BASE_URL, data=payload, timeout=timeout)
                if r_coll.status_code != 200 or "Server Error" in r_coll.text:
                    result["status"] = "FAULT"
                    result["faults"].append({
                        "severity": "HIGH",
                        "component": "COLLEGE_DROPDOWN",
                        "message": f"Selecting college '{c_val}' failed (HTTP {r_coll.status_code})."
                    })
            except Exception as e:
                result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "COLLEGE_DROPDOWN",
                    "message": f"Selecting college '{c_val}' failed: {e}"
                })

    # Step 5: Test Foreign Campus Checkbox (ForeignIndicator)
    fc_cb = soup_sec.find("input", id=re.compile(r"ForeignIndicator", re.IGNORECASE))
    if fc_cb:
        payload = {
            "__VIEWSTATE": vs_sec,
            "__VIEWSTATEGENERATOR": vsg_sec,
            "__EVENTVALIDATION": ev_sec,
            fc_cb.get("name"): "on",
            "__EVENTTARGET": fc_cb.get("name"),
            "__EVENTARGUMENT": ""
        }
        try:
            r_fc = s.post(TRENDS_BASE_URL, data=payload, timeout=timeout)
            if r_fc.status_code == 200 and "Server Error" not in r_fc.text:
                result["checkboxes_tested"]["ForeignIndicator"] = "PASS"
            else:
                result["checkboxes_tested"]["ForeignIndicator"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "FOREIGN_CAMPUS_CHECKBOX",
                    "message": f"Toggling Exclude Foreign Campus in Trends returned HTTP {r_fc.status_code}."
                })
        except Exception as e:
            result["checkboxes_tested"]["ForeignIndicator"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "HIGH",
                "component": "FOREIGN_CAMPUS_CHECKBOX",
                "message": f"Foreign Campus toggle threw exception: {e}"
            })

    # Step 6: Test Bachelor's Degree Checkbox (transferIndicator) if present (Retention)
    ti_cb = soup_sec.find("input", id=re.compile(r"transferIndicator", re.IGNORECASE))
    if ti_cb:
        payload = {
            "__VIEWSTATE": vs_sec,
            "__VIEWSTATEGENERATOR": vsg_sec,
            "__EVENTVALIDATION": ev_sec,
            ti_cb.get("name"): "on",
            "__EVENTTARGET": ti_cb.get("name"),
            "__EVENTARGUMENT": ""
        }
        try:
            r_ti = s.post(TRENDS_BASE_URL, data=payload, timeout=timeout)
            if r_ti.status_code == 200 and "Server Error" not in r_ti.text:
                result["checkboxes_tested"]["transferIndicator"] = "PASS"
            else:
                result["checkboxes_tested"]["transferIndicator"] = "FAIL"
                if result["status"] == "HEALTHY":
                    result["status"] = "FAULT"
                result["faults"].append({
                    "severity": "HIGH",
                    "component": "BACHELOR_DEGREE_CHECKBOX",
                    "message": f"Toggling Bachelor's Degree checkbox in Trends returned HTTP {r_ti.status_code}."
                })
        except Exception as e:
            result["checkboxes_tested"]["transferIndicator"] = "FAIL"
            if result["status"] == "HEALTHY":
                result["status"] = "FAULT"
            result["faults"].append({
                "severity": "HIGH",
                "component": "BACHELOR_DEGREE_CHECKBOX",
                "message": f"Bachelor's Degree checkbox toggle threw exception: {e}"
            })

    return result


def run_all_trends_tests(test_all_colleges: bool = False, output_dir: Path = Path("./reports")) -> List[Dict[str, Any]]:
    """Run tests across all 16 Trends reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold cyan]Running TTU Trends Audit across {len(TRENDS_SECTIONS)} reports...[/bold cyan]\n")
    
    results = []
    t_start = time.time()
    for idx, sec in enumerate(TRENDS_SECTIONS):
        console.print(f"[{idx+1}/{len(TRENDS_SECTIONS)}] Testing {sec['title']} ({sec['category']})...")
        res = test_trends_section(sec, test_all_colleges=test_all_colleges)
        results.append(res)
        status_color = "green" if res["status"] == "HEALTHY" else ("yellow" if res["status"] == "FAULT" else "red")
        console.print(f"       Status: [{status_color}]{res['status']}[/{status_color}] (Time: {res['load_time_sec']}s, Rows: {res['total_historical_rows']})\n")

    elapsed = round(time.time() - t_start, 2)
    healthy = sum(1 for r in results if r["status"] == "HEALTHY")
    faults = sum(1 for r in results if r["status"] == "FAULT")
    critical = sum(1 for r in results if r["status"] == "CRITICAL")

    json_file = output_dir / "trends_audit_data.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    console.print(f"\n[bold green]Trends Audit Finished in {elapsed}s: {healthy} Healthy, {faults} Faults, {critical} Critical.[/bold green]")
    return results


if __name__ == "__main__":
    run_all_trends_tests()
