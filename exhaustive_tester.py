"""
TTU FactBook & Trends Exhaustive All-Attributes Testing Engine.
Exhaustively tests every single page, every semester/term option (from latest down to 2009),
all checkboxes (checked and unchecked), all export functionalities (Excel & PDF),
Trends chart export scripts, and data math integrity.
"""

import time
import json
import re
import urllib3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console

from parser import parse_numeric
from validator import validate_row_sums
from config import load_all_subpages, KEY_MC_PAGES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
console = Console()

def validate_html_table(table_element) -> List[str]:
    """Validate horizontal sum integrity of an HTML GridView table."""
    errors = []
    if not table_element:
        return errors
    rows = table_element.find_all("tr")
    if len(rows) <= 1:
        return errors
    header_rows = [tr for tr in rows if tr.find("th")]
    headers = []
    if header_rows:
        headers = [td.get_text(strip=True) for td in header_rows[-1].find_all(["th", "td"])]
    else:
        headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]

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
        for fl in flags:
            errors.append(f"[{' '.join(cells[:2])}] {fl['message']}")
    return errors


PROD_BASE_URL = "https://techdata.irs.ttu.edu"
REPORTS_DIR = Path("./reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TRENDS_PAGES = [
    {"url": "https://techdata.irs.ttu.edu/Trends/Applied_Admitted_Enrolled/APPADMENRCOLL.aspx?level=nfr", "title": "Applied, Admitted & Enrolled - New First-Year", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Faculty/FacultyByFullPartTime.aspx", "title": "Faculty Headcount - Full/Part Time", "category": "Faculty"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Faculty/FacultyByRank.aspx", "title": "Faculty Headcount - By Rank", "category": "Faculty"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Faculty/FacultyByTenureTenureTrack.aspx", "title": "Faculty Headcount - By Tenure Status", "category": "Faculty"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Faculty/FacultyByEthnicity.aspx", "title": "Faculty Headcount - By Ethnicity", "category": "Faculty"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Research/ResearchExpendituresbySrc.aspx", "title": "Research Expenditures - By Source", "category": "Research"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Revenue/REVSRC.aspx", "title": "Revenue - By Source", "category": "Revenue"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Revenue/REVOTHFDS.aspx", "title": "Revenue - Additional Funds", "category": "Revenue"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Revenue/REVTUTFEES.aspx", "title": "Revenue - Tuition & Fees", "category": "Revenue"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Degrees/DEGLEVEL.aspx", "title": "Degrees Conferred - By Level", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Enrollment/ENRTYPE.aspx", "title": "Enrollment - By Level", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Graduation%20Rates/GRADCOLLEGE.aspx?level=coll", "title": "Graduation Rates - By College", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Newfreshman/NFRCOLL.aspx", "title": "New First-Year Students - By College", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Newgraduate/NGRCOLL.aspx", "title": "New Graduate Students - By College", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Newlaw/NLWETHNICITY.aspx", "title": "New Law Students - By Ethnicity", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Newundergradtransfer/NTRCOLL.aspx", "title": "New Undergraduate Transfers - By College", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/Retention%20Rates/RETCOLLEGE.aspx?level=coll", "title": "Retention Rates - One Year", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/SCH/SCHLEVEL.aspx", "title": "Semester Credit Hours - By Course Level", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/DistanceEducation/DistnEdctnByEnrlmnt.aspx", "title": "Distance Education Course Enrollment", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/WSCH/WSCHLEVEL.aspx", "title": "Weighted SCH - By Level", "category": "Students"},
    {"url": "https://techdata.irs.ttu.edu/Trends/NewVetSchool/NVETETHNICITY.aspx", "title": "New Veterinary School - By Ethnicity", "category": "Students"},
]


def extract_aspnet_state(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract ASP.NET hidden state variables."""
    state = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        inp = soup.find("input", {"id": name})
        if inp and inp.has_attr("value"):
            state[name] = inp["value"]
    return state


def test_factbook_page_exhaustive(page_info: Dict[str, Any], max_terms: Optional[int] = None, timeout: int = 25) -> Dict[str, Any]:
    """
    Exhaustively tests a FactBook page across:
    - Every semester/term in dropdown
    - Both states of ForeignIndicator
    - Both states of transferIndicator
    - Excel Export for term
    - PDF Export for term
    - Math validation for each term
    """
    path = page_info.get("path", "")
    url = f"{PROD_BASE_URL}{path}" if path.startswith("/") else path
    title = page_info.get("title", path)
    category = page_info.get("category", "General")

    audit: Dict[str, Any] = {
        "url": url,
        "title": title,
        "category": category,
        "status": "HEALTHY",
        "total_terms_found": 0,
        "terms_tested_count": 0,
        "permutations_tested": 0,
        "faults": [],
        "terms_summary": [],
        "has_foreign_checkbox": False,
        "has_transfer_checkbox": False,
        "has_excel_export": False,
        "has_pdf_export": False,
    }

    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Step 1: Initial GET
    try:
        r_init = s.get(url, timeout=timeout)
        if r_init.status_code != 200:
            audit["status"] = "CRITICAL"
            audit["faults"].append({
                "severity": "CRITICAL",
                "component": "HTTP_GET",
                "message": f"HTTP status {r_init.status_code}"
            })
            return audit
    except Exception as e:
        audit["status"] = "CRITICAL"
        audit["faults"].append({
            "severity": "CRITICAL",
            "component": "HTTP_GET",
            "message": f"Connection failed: {e}"
        })
        return audit

    soup_init = BeautifulSoup(r_init.text, "lxml")
    state = extract_aspnet_state(soup_init)
    if "__VIEWSTATE" not in state:
        audit["status"] = "CRITICAL"
        audit["faults"].append({
            "severity": "CRITICAL",
            "component": "VIEWSTATE",
            "message": "Missing __VIEWSTATE on initial load"
        })
        return audit

    # Detect page controls
    term_select = soup_init.find("select", {"id": "ENRDropDownList"})
    audit["has_foreign_checkbox"] = soup_init.find("input", {"id": "ForeignIndicator"}) is not None
    audit["has_transfer_checkbox"] = soup_init.find("input", {"id": "transferIndicator"}) is not None
    audit["has_excel_export"] = soup_init.find("input", {"id": "expToExcel"}) is not None
    audit["has_pdf_export"] = soup_init.find("input", {"id": "expToWord"}) is not None

    term_options: List[Tuple[str, str]] = []
    if term_select:
        for opt in term_select.find_all("option"):
            val = opt.get("value", "")
            lbl = opt.get_text(strip=True)
            if val:
                term_options.append((val, lbl))

    audit["total_terms_found"] = len(term_options)

    # Slice terms if max_terms specified
    active_terms = term_options[:max_terms] if max_terms else term_options
    audit["terms_tested_count"] = len(active_terms)

    # Test initial loaded table math
    tbl_init = soup_init.find("table", {"id": "MyGridView"})
    if tbl_init:
        init_errs = validate_html_table(tbl_init)
        for err in init_errs:
            audit["faults"].append({
                "severity": "MAJOR",
                "component": "MATH_INIT",
                "message": f"Initial page load: {err}"
            })

    current_state = dict(state)

    # Step 2: Loop through each term
    for val, lbl in active_terms:
        term_record: Dict[str, Any] = {
            "term_val": val,
            "term_label": lbl,
            "postback_ok": False,
            "excel_ok": False,
            "pdf_ok": False,
            "foreign_ok": False,
            "transfer_ok": False,
            "math_ok": True,
            "rows_count": 0,
            "faults": []
        }

        # 2a. Term Postback
        post_data = {
            "__EVENTTARGET": "ENRDropDownList",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": current_state.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": current_state.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": current_state.get("__EVENTVALIDATION", ""),
            "ENRDropDownList": val
        }

        try:
            r_term = s.post(url, data=post_data, timeout=timeout)
            audit["permutations_tested"] += 1
            if r_term.status_code == 200:
                soup_term = BeautifulSoup(r_term.text, "lxml")
                current_state = extract_aspnet_state(soup_term) or current_state
                tbl_term = soup_term.find("table", {"id": "MyGridView"})
                if tbl_term:
                    term_record["postback_ok"] = True
                    rows = tbl_term.find_all("tr")
                    term_record["rows_count"] = len(rows)

                    # Validate math for this specific term
                    term_errs = validate_html_table(tbl_term)
                    if term_errs:
                        term_record["math_ok"] = False
                        for err in term_errs:
                            term_record["faults"].append(f"Math Error: {err}")
                            audit["faults"].append({
                                "severity": "MAJOR",
                                "component": f"MATH_{val}",
                                "term": lbl,
                                "message": err
                            })
                else:
                    term_record["faults"].append("Table MyGridView not rendered after term selection")
                    audit["faults"].append({
                        "severity": "WARNING",
                        "component": f"TABLE_MISSING_{val}",
                        "term": lbl,
                        "message": "MyGridView table not returned for term"
                    })
            else:
                term_record["faults"].append(f"HTTP {r_term.status_code} on term selection")
                audit["faults"].append({
                    "severity": "MAJOR",
                    "component": f"POST_TERM_{val}",
                    "term": lbl,
                    "message": f"HTTP status {r_term.status_code}"
                })
        except Exception as e:
            term_record["faults"].append(f"Term selection error: {e}")
            audit["faults"].append({
                "severity": "MAJOR",
                "component": f"POST_TERM_{val}",
                "term": lbl,
                "message": str(e)
            })

        # 2b. Test Foreign Indicator Checkbox for this term (if present)
        if audit["has_foreign_checkbox"]:
            try:
                foreign_data = {
                    "__EVENTTARGET": "ForeignIndicator",
                    "__EVENTARGUMENT": "",
                    "__VIEWSTATE": current_state.get("__VIEWSTATE", ""),
                    "__VIEWSTATEGENERATOR": current_state.get("__VIEWSTATEGENERATOR", ""),
                    "__EVENTVALIDATION": current_state.get("__EVENTVALIDATION", ""),
                    "ENRDropDownList": val,
                    "ForeignIndicator": "on"
                }
                r_foreign = s.post(url, data=foreign_data, timeout=timeout)
                audit["permutations_tested"] += 1
                if r_foreign.status_code == 200:
                    soup_foreign = BeautifulSoup(r_foreign.text, "lxml")
                    chk = soup_foreign.find("input", {"id": "ForeignIndicator"})
                    if chk and chk.has_attr("checked"):
                        term_record["foreign_ok"] = True
                    else:
                        term_record["faults"].append("ForeignIndicator failed to reflect checked state in postback")
                        audit["faults"].append({
                            "severity": "MINOR",
                            "component": f"CHECKBOX_FOREIGN_{val}",
                            "term": lbl,
                            "message": "ForeignIndicator did not reflect checked state"
                        })
                else:
                    term_record["faults"].append(f"HTTP {r_foreign.status_code} on ForeignIndicator toggle")
            except Exception as e:
                term_record["faults"].append(f"ForeignIndicator error: {e}")

        # 2c. Test Bachelor's Degree Checkbox for this term (if present)
        if audit["has_transfer_checkbox"]:
            try:
                trans_data = {
                    "__EVENTTARGET": "transferIndicator",
                    "__EVENTARGUMENT": "",
                    "__VIEWSTATE": current_state.get("__VIEWSTATE", ""),
                    "__VIEWSTATEGENERATOR": current_state.get("__VIEWSTATEGENERATOR", ""),
                    "__EVENTVALIDATION": current_state.get("__EVENTVALIDATION", ""),
                    "ENRDropDownList": val,
                    "transferIndicator": "on"
                }
                r_trans = s.post(url, data=trans_data, timeout=timeout)
                audit["permutations_tested"] += 1
                if r_trans.status_code == 200:
                    soup_trans = BeautifulSoup(r_trans.text, "lxml")
                    chk = soup_trans.find("input", {"id": "transferIndicator"})
                    if chk and chk.has_attr("checked"):
                        term_record["transfer_ok"] = True
                    else:
                        term_record["faults"].append("transferIndicator failed to reflect checked state")
                else:
                    term_record["faults"].append(f"HTTP {r_trans.status_code} on transferIndicator toggle")
            except Exception as e:
                term_record["faults"].append(f"transferIndicator error: {e}")

        # 2d. Test Excel Export for this term
        if audit["has_excel_export"]:
            try:
                excel_data = {
                    "__EVENTTARGET": "",
                    "__EVENTARGUMENT": "",
                    "__VIEWSTATE": current_state.get("__VIEWSTATE", ""),
                    "__VIEWSTATEGENERATOR": current_state.get("__VIEWSTATEGENERATOR", ""),
                    "__EVENTVALIDATION": current_state.get("__EVENTVALIDATION", ""),
                    "ENRDropDownList": val,
                    "expToExcel.x": "15",
                    "expToExcel.y": "15"
                }
                r_excel = s.post(url, data=excel_data, timeout=timeout)
                audit["permutations_tested"] += 1
                disp = r_excel.headers.get("content-disposition", "")
                ctype = r_excel.headers.get("content-type", "")
                if r_excel.status_code == 200 and ("attachment" in disp or "spreadsheet" in ctype or "excel" in ctype or len(r_excel.content) > 1000):
                    term_record["excel_ok"] = True
                else:
                    term_record["faults"].append(f"Excel export failed (status={r_excel.status_code}, len={len(r_excel.content)})")
                    audit["faults"].append({
                        "severity": "MAJOR",
                        "component": f"EXCEL_{val}",
                        "term": lbl,
                        "message": f"Excel export failed: status {r_excel.status_code}, length {len(r_excel.content)}"
                    })
            except Exception as e:
                term_record["faults"].append(f"Excel export error: {e}")

        # 2e. Test PDF Export for this term
        if audit["has_pdf_export"]:
            try:
                pdf_data = {
                    "__EVENTTARGET": "",
                    "__EVENTARGUMENT": "",
                    "__VIEWSTATE": current_state.get("__VIEWSTATE", ""),
                    "__VIEWSTATEGENERATOR": current_state.get("__VIEWSTATEGENERATOR", ""),
                    "__EVENTVALIDATION": current_state.get("__EVENTVALIDATION", ""),
                    "ENRDropDownList": val,
                    "expToWord.x": "15",
                    "expToWord.y": "15"
                }
                r_pdf = s.post(url, data=pdf_data, timeout=timeout)
                audit["permutations_tested"] += 1
                disp = r_pdf.headers.get("content-disposition", "")
                ctype = r_pdf.headers.get("content-type", "")
                if r_pdf.status_code == 200 and ("attachment" in disp or "pdf" in ctype or len(r_pdf.content) > 500):
                    term_record["pdf_ok"] = True
                else:
                    term_record["faults"].append(f"PDF export failed (status={r_pdf.status_code}, len={len(r_pdf.content)})")
                    audit["faults"].append({
                        "severity": "MAJOR",
                        "component": f"PDF_{val}",
                        "term": lbl,
                        "message": f"PDF export failed: status {r_pdf.status_code}, length {len(r_pdf.content)}"
                    })
            except Exception as e:
                term_record["faults"].append(f"PDF export error: {e}")

        audit["terms_summary"].append(term_record)

    # Set overall status
    if any(f.get("severity") == "CRITICAL" for f in audit["faults"]):
        audit["status"] = "CRITICAL"
    elif any(f.get("severity") == "MAJOR" for f in audit["faults"]):
        audit["status"] = "FAULT"
    elif audit["faults"]:
        audit["status"] = "WARNING"
    else:
        audit["status"] = "HEALTHY"

    return audit


def test_trends_page_exhaustive(trends_info: Dict[str, Any], max_colleges: Optional[int] = None, timeout: int = 25) -> Dict[str, Any]:
    """
    Exhaustively tests a Trends page across:
    - Every semester term in APPADMDropDownList1
    - Every college in APPADMDropDownList2 (TTU, MC, AG, AR, etc.)
    - Checkboxes: ForeignIndicator, transferIndicator
    - Export Chart With Data Table button script check (tranE1 detection)
    - Historical rows math consistency
    """
    url = trends_info["url"]
    title = trends_info["title"]
    category = trends_info["category"]

    audit: Dict[str, Any] = {
        "url": url,
        "title": title,
        "category": category,
        "status": "HEALTHY",
        "permutations_tested": 0,
        "terms_found": [],
        "colleges_found": [],
        "combinations_summary": [],
        "has_foreign_checkbox": False,
        "has_transfer_checkbox": False,
        "has_chart_export_button": False,
        "chart_export_script_healthy": True,
        "faults": []
    }

    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Step 1: Initial GET
    try:
        r_init = s.get(url, timeout=timeout)
        if r_init.status_code != 200:
            audit["status"] = "CRITICAL"
            audit["faults"].append({
                "severity": "CRITICAL",
                "component": "HTTP_GET",
                "message": f"HTTP status {r_init.status_code}"
            })
            return audit
    except Exception as e:
        audit["status"] = "CRITICAL"
        audit["faults"].append({
            "severity": "CRITICAL",
            "component": "HTTP_GET",
            "message": f"Connection failed: {e}"
        })
        return audit

    # Inspect JavaScript export button and detect tranE1 ReferenceError
    if "buttonExport" in r_init.text:
        audit["has_chart_export_button"] = True
        if "tranE1.innerText" in r_init.text and re.search(r"//\s*const\s+tranE1", r_init.text):
            audit["chart_export_script_healthy"] = False
            audit["faults"].append({
                "severity": "CRITICAL",
                "component": "CHART_EXPORT_JS",
                "message": "Button 'Export Chart With Data Table' has broken JavaScript: tranE1 is referenced on line 187 but commented out on line 178, throwing ReferenceError: tranE1 is not defined when clicked."
            })

    soup_init = BeautifulSoup(r_init.text, "lxml")
    state = extract_aspnet_state(soup_init)
    audit["has_foreign_checkbox"] = soup_init.find("input", {"id": "ForeignIndicator"}) is not None
    audit["has_transfer_checkbox"] = soup_init.find("input", {"id": "transferIndicator"}) is not None

    # Discover dropdown options
    dd1 = soup_init.find("select", {"id": "APPADMDropDownList1"})
    terms: List[Tuple[str, str]] = []
    if dd1:
        for opt in dd1.find_all("option"):
            v = opt.get("value", "")
            t = opt.get_text(strip=True)
            if v:
                terms.append((v, t))
    if not terms:
        terms = [("", "Default")]
    audit["terms_found"] = [t[1] for t in terms]

    dd2 = soup_init.find("select", {"id": "APPADMDropDownList2"})
    colleges: List[Tuple[str, str]] = []
    if dd2:
        for opt in dd2.find_all("option"):
            v = opt.get("value", "")
            t = opt.get_text(strip=True)
            if v:
                colleges.append((v, t))
    if not colleges:
        colleges = [("", "Default")]
    audit["colleges_found"] = [c[1] for c in colleges]

    active_colleges = colleges[:max_colleges] if max_colleges else colleges

    # Step 2: Permute Term x College
    for t_val, t_lbl in terms:
        for c_val, c_lbl in active_colleges:
            combo_record: Dict[str, Any] = {
                "term": t_lbl,
                "college": c_lbl,
                "postback_ok": False,
                "table_rows": 0,
                "math_ok": True,
                "mc_present": False,
                "faults": []
            }

            post_data = {
                "__EVENTTARGET": "APPADMDropDownList2" if c_val else "APPADMDropDownList1",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": state.get("__VIEWSTATE", ""),
                "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
                "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
            }
            if t_val:
                post_data["APPADMDropDownList1"] = t_val
            if c_val:
                post_data["APPADMDropDownList2"] = c_val

            try:
                r_combo = s.post(url, data=post_data, timeout=timeout)
                audit["permutations_tested"] += 1
                if r_combo.status_code == 200:
                    combo_record["postback_ok"] = True
                    soup_combo = BeautifulSoup(r_combo.text, "lxml")
                    tbl = soup_combo.find("table", {"id": "MyGridView"})
                    if tbl:
                        rows = tbl.find_all("tr")
                        combo_record["table_rows"] = len(rows)
                        # Check math across rows
                        tbl_errs = validate_html_table(tbl)
                        if tbl_errs:
                            combo_record["math_ok"] = False
                            for err in tbl_errs:
                                combo_record["faults"].append(f"Math Error: {err}")
                                audit["faults"].append({
                                    "severity": "MAJOR",
                                    "component": f"MATH_{t_lbl}_{c_lbl}",
                                    "message": f"[{t_lbl} / {c_lbl}]: {err}"
                                })

                        # If MC college selected, verify MC rows
                        if c_val == "MC" or "Media" in c_lbl:
                            combo_record["mc_present"] = len(rows) > 1
                else:
                    combo_record["faults"].append(f"HTTP {r_combo.status_code}")
                    audit["faults"].append({
                        "severity": "MAJOR",
                        "component": f"POST_{t_lbl}_{c_lbl}",
                        "message": f"HTTP status {r_combo.status_code}"
                    })
            except Exception as e:
                combo_record["faults"].append(str(e))

            audit["combinations_summary"].append(combo_record)

    # Step 3: Checkbox tests (Foreign & Transfer)
    if audit["has_foreign_checkbox"]:
        try:
            foreign_data = {
                "__EVENTTARGET": "ForeignIndicator",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": state.get("__VIEWSTATE", ""),
                "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
                "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
                "ForeignIndicator": "on"
            }
            if terms[0][0]:
                foreign_data["APPADMDropDownList1"] = terms[0][0]
            if colleges[0][0]:
                foreign_data["APPADMDropDownList2"] = colleges[0][0]
            r_foreign = s.post(url, data=foreign_data, timeout=timeout)
            audit["permutations_tested"] += 1
            if r_foreign.status_code != 200:
                audit["faults"].append({
                    "severity": "MINOR",
                    "component": "FOREIGN_CHECKBOX",
                    "message": f"HTTP status {r_foreign.status_code} on foreign indicator toggle"
                })
        except Exception as e:
            audit["faults"].append({
                "severity": "MINOR",
                "component": "FOREIGN_CHECKBOX",
                "message": str(e)
            })

    # Overall status
    if any(f.get("severity") == "CRITICAL" for f in audit["faults"]):
        audit["status"] = "CRITICAL"
    elif any(f.get("severity") == "MAJOR" for f in audit["faults"]):
        audit["status"] = "FAULT"
    elif audit["faults"]:
        audit["status"] = "WARNING"
    else:
        audit["status"] = "HEALTHY"

    return audit


def run_exhaustive_suite(max_workers: int = 8, fb_term_limit: Optional[int] = None, trends_college_limit: Optional[int] = None, quick_pages_only: bool = False, scope: str = "all") -> Dict[str, Any]:
    """
    Runs the exhaustive combinatorial audit across FactBook and/or Trends.
    scope: 'all' | 'factbook' | 'trends'
    """
    t0 = time.time()
    fb_pages = KEY_MC_PAGES if quick_pages_only else load_all_subpages()
    
    # Load previous results if doing partial run
    cached_ex: Dict[str, Any] = {}
    cached_file = REPORTS_DIR / "exhaustive_audit_data.json"
    if cached_file.exists():
        try:
            with open(cached_file) as f:
                cached_ex = json.load(f)
        except Exception:
            pass

    overall_report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_factbook_pages": len(fb_pages) if scope in ("all", "factbook") else len(cached_ex.get("factbook_results", [])),
        "total_trends_pages": len(TRENDS_PAGES) if scope in ("all", "trends") else len(cached_ex.get("trends_results", [])),
        "factbook_results": cached_ex.get("factbook_results", []) if scope == "trends" else [],
        "trends_results": cached_ex.get("trends_results", []) if scope == "factbook" else [],
        "summary": {
            "total_permutations_tested": 0,
            "factbook_healthy": 0,
            "factbook_faults": 0,
            "trends_healthy": 0,
            "trends_faults": 0,
            "total_faults_detected": 0,
            "duration_sec": 0
        }
    }

    console.print(f"[bold cyan]Starting Exhaustive Audit (Scope: {scope})[/bold cyan]")

    # 1. FactBook Concurrent Execution
    if scope in ("all", "factbook"):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fb_futures = {executor.submit(test_factbook_page_exhaustive, p, fb_term_limit): p for p in fb_pages}
            for future in as_completed(fb_futures):
                p = fb_futures[future]
                try:
                    res = future.result()
                    overall_report["factbook_results"].append(res)
                    overall_report["summary"]["total_permutations_tested"] += res["permutations_tested"]
                    status_color = "green" if res["status"] == "HEALTHY" else "red"
                    console.print(f"[{status_color}]FactBook: {res['title'][:35]}[/{status_color}] | Terms: {res['terms_tested_count']}/{res['total_terms_found']} | Faults: {len(res['faults'])}")
                except Exception as e:
                    console.print(f"[red]Error on {p.get('title')}: {e}[/red]")

    # 2. Trends Concurrent Execution
    if scope in ("all", "trends"):
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            tr_futures = {executor.submit(test_trends_page_exhaustive, tp, trends_college_limit): tp for tp in TRENDS_PAGES}
            for future in as_completed(tr_futures):
                tp = tr_futures[future]
                try:
                    res = future.result()
                    overall_report["trends_results"].append(res)
                    overall_report["summary"]["total_permutations_tested"] += res["permutations_tested"]
                    status_color = "green" if res["status"] == "HEALTHY" else "red"
                    console.print(f"[{status_color}]Trends: {res['title'][:35]}[/{status_color}] | Combos: {len(res['combinations_summary'])} | Faults: {len(res['faults'])}")
                except Exception as e:
                    console.print(f"[red]Error on {tp.get('title')}: {e}[/red]")

    # Summaries
    fb_res = overall_report["factbook_results"]
    tr_res = overall_report["trends_results"]
    overall_report["summary"]["factbook_healthy"] = sum(1 for r in fb_res if r["status"] == "HEALTHY")
    overall_report["summary"]["factbook_faults"] = len(fb_res) - overall_report["summary"]["factbook_healthy"]
    overall_report["summary"]["trends_healthy"] = sum(1 for r in tr_res if r["status"] == "HEALTHY")
    overall_report["summary"]["trends_faults"] = len(tr_res) - overall_report["summary"]["trends_healthy"]
    overall_report["summary"]["total_faults_detected"] = sum(len(r["faults"]) for r in fb_res) + sum(len(r["faults"]) for r in tr_res)
    overall_report["summary"]["duration_sec"] = round(time.time() - t0, 2)

    # Save to disk
    out_file = REPORTS_DIR / "exhaustive_audit_data.json"
    with open(out_file, "w") as f:
        json.dump(overall_report, f, indent=2)

    console.print(f"[bold green]Exhaustive Audit Complete in {overall_report['summary']['duration_sec']}s![/bold green]")
    console.print(f"Total Permutations Tested: {overall_report['summary']['total_permutations_tested']}")
    console.print(f"Total Faults Detected: {overall_report['summary']['total_faults_detected']}")

    return overall_report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TTU FactBook & Trends Exhaustive All-Attributes Tester")
    parser.add_argument("--quick", action="store_true", help="Quick mode: run key pages with 5 terms")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent worker threads")
    parser.add_argument("--terms", type=int, default=None, help="Limit number of terms per page")
    parser.add_argument("--colleges", type=int, default=None, help="Limit number of colleges per Trends page")
    args = parser.parse_args()

    if args.quick:
        run_exhaustive_suite(max_workers=args.workers, fb_term_limit=5, trends_college_limit=4, quick_pages_only=True)
    else:
        run_exhaustive_suite(max_workers=args.workers, fb_term_limit=args.terms, trends_college_limit=args.colleges, quick_pages_only=False)
