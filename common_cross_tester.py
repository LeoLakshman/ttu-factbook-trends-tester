"""
TTU FactBook vs Trends Common Data Cross-Verification Engine.
Identifies reports that exist in both TTU FactBook and TTU Trends,
cross-verifies matching metrics cell-by-cell (cohorts, applied, admitted, degrees, retention, graduation),
and flags discrepancies between the two systems.
"""

import time
import json
import re
import urllib3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPORTS_DIR = Path("./reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PROD_BASE_URL = "https://techdata.irs.ttu.edu"

# Common reports present in both FactBook and Trends
COMMON_REPORTS = [
    {
        "id": "applied_admitted_nfr",
        "title": "Applied & Admitted - New First-Year Students",
        "category": "Admissions",
        "factbook_url": "https://techdata.irs.ttu.edu/FactBook/AppliedAdmitted/APPADMCOLL.aspx?level=nfr",
        "trends_url": "https://techdata.irs.ttu.edu/Trends/Applied_Admitted_Enrolled/APPADMENRCOLL.aspx?level=nfr",
        "terms_to_compare": [
            {"year": "2024", "fb_term_code": "20252", "fb_term_label": "Fall/Summer 2024", "tr_term_code": "27", "tr_term_label": "Fall"},
            {"year": "2023", "fb_term_code": "20242", "fb_term_label": "Fall/Summer 2023", "tr_term_code": "27", "tr_term_label": "Fall"},
            {"year": "2022", "fb_term_code": "20232", "fb_term_label": "Fall/Summer 2022", "tr_term_code": "27", "tr_term_label": "Fall"},
            {"year": "2021", "fb_term_code": "20222", "fb_term_label": "Fall/Summer 2021", "tr_term_code": "27", "tr_term_label": "Fall"},
            {"year": "2020", "fb_term_code": "20212", "fb_term_label": "Fall/Summer 2020", "tr_term_code": "27", "tr_term_label": "Fall"},
        ],
        "colleges_to_check": ["TTU", "MC", "AG", "AR", "AS", "BA", "ED", "EN", "HS", "VP"]
    },
    {
        "id": "degrees_conferred",
        "title": "Degrees Conferred - By Level & College",
        "category": "Degrees",
        "factbook_url": "https://techdata.irs.ttu.edu/FactBook/Degree/DEGCOLL.aspx",
        "trends_url": "https://techdata.irs.ttu.edu/Trends/Degrees/DEGLEVEL.aspx",
        "terms_to_compare": [
            {"year": "2026", "fb_term_code": "2026", "fb_term_label": "FY 2025-2026", "tr_year": "FY2026", "tr_term_code": "FY"},
            {"year": "2025", "fb_term_code": "2025", "fb_term_label": "FY 2024-2025", "tr_year": "FY2025", "tr_term_code": "FY"},
            {"year": "2024", "fb_term_code": "2024", "fb_term_label": "FY 2023-2024", "tr_year": "FY2024", "tr_term_code": "FY"},
            {"year": "2023", "fb_term_code": "2023", "fb_term_label": "FY 2022-2023", "tr_year": "FY2023", "tr_term_code": "FY"},
            {"year": "2022", "fb_term_code": "2022", "fb_term_label": "FY 2021-2022", "tr_year": "FY2022", "tr_term_code": "FY"},
            {"year": "2021", "fb_term_code": "2021", "fb_term_label": "FY 2020-2021", "tr_year": "FY2021", "tr_term_code": "FY"},
        ],
        "colleges_to_check": ["TTU", "MC", "AG", "AR", "AS", "BA", "ED", "EN"]
    },
    {
        "id": "retention_rates_1yr",
        "title": "Retention Rates - 1-Year Cohort Retention",
        "category": "Retention",
        "factbook_url": "https://techdata.irs.ttu.edu/FactBook/Retention/RETCOLL.aspx?level=1",
        "trends_url": "https://techdata.irs.ttu.edu/Trends/Retention%20Rates/RETCOLLEGE.aspx?level=coll",
        "terms_to_compare": [
            {"year": "2025", "fb_term_code": "20262", "fb_term_label": "Fall 2025", "tr_year": "2025"},
            {"year": "2024", "fb_term_code": "20252", "fb_term_label": "Fall 2024", "tr_year": "2024"},
            {"year": "2023", "fb_term_code": "20242", "fb_term_label": "Fall 2023", "tr_year": "2023"},
            {"year": "2022", "fb_term_code": "20232", "fb_term_label": "Fall 2022", "tr_year": "2022"},
            {"year": "2021", "fb_term_code": "20222", "fb_term_label": "Fall 2021", "tr_year": "2021"},
            {"year": "2020", "fb_term_code": "20212", "fb_term_label": "Fall 2020", "tr_year": "2020"},
        ],
        "colleges_to_check": ["TTU", "MC", "AG", "AR", "AS", "BA", "ED", "EN"]
    },
    {
        "id": "graduation_rates_4yr",
        "title": "Graduation Rates - 4-Year College Rates",
        "category": "Graduation",
        "factbook_url": "https://techdata.irs.ttu.edu/FactBook/Graduation/GRADCOLL.aspx?level=4",
        "trends_url": "https://techdata.irs.ttu.edu/Trends/Graduation%20Rates/GRADCOLLEGE.aspx?level=coll",
        "terms_to_compare": [
            {"year": "2020", "fb_term_code": "20212", "fb_term_label": "Fall 2020", "tr_year": "2020"},
            {"year": "2019", "fb_term_code": "20202", "fb_term_label": "Fall 2019", "tr_year": "2019"},
            {"year": "2018", "fb_term_code": "20192", "fb_term_label": "Fall 2018", "tr_year": "2018"},
        ],
        "colleges_to_check": ["TTU", "MC", "AG", "AR", "AS", "BA", "ED", "EN"]
    }
]


def get_fresh_session() -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return s


def robust_fetch(session: requests.Session, method: str, url: str, max_retries: int = 2, timeout: int = 45, **kwargs) -> Optional[requests.Response]:
    """Robust request with retry and backoff to handle slow loads and transient 404/500/timeout issues."""
    for attempt in range(max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = session.get(url, timeout=timeout, **kwargs)
            else:
                resp = session.post(url, timeout=timeout, **kwargs)
            if resp.status_code == 200:
                return resp
            elif resp.status_code in (404, 500, 502, 503) and attempt < max_retries:
                time.sleep(1.2)
                continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < max_retries:
                time.sleep(1.5)
                continue
            return None
        except Exception:
            return None
    return None


def extract_aspnet_state(soup: BeautifulSoup) -> Dict[str, str]:
    state = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        inp = soup.find("input", {"id": name})
        if inp and inp.has_attr("value"):
            state[name] = inp["value"]
    return state


def parse_factbook_gridview(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    grid = soup.find("table", {"id": "MyGridView"})
    if not grid:
        return {}
    rows = grid.find_all("tr")
    if len(rows) <= 1:
        return {}
    
    header_tr = rows[0]
    headers = [th.get_text(strip=True).upper() for th in header_tr.find_all(["th", "td"])]
    data: Dict[str, Dict[str, str]] = {}

    for tr in rows[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if not cells:
            continue
        code = cells[0].strip().upper()
        row_dict = {}
        for idx, c in enumerate(cells):
            h = headers[idx] if idx < len(headers) else f"COL_{idx}"
            row_dict[h] = c
        data[code] = row_dict
    return data


def parse_trends_gridview(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    grid = soup.find("table", {"id": "MyGridView"})
    if not grid:
        return {}
    rows = grid.find_all("tr")
    if len(rows) <= 1:
        return {}

    header_tr = rows[0]
    headers = [th.get_text(strip=True) for th in header_tr.find_all(["th", "td"])]
    data: Dict[str, Dict[str, str]] = {}

    for tr in rows[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
        if not cells:
            continue
        year_key = cells[0].strip()
        row_dict = {}
        for idx, c in enumerate(cells):
            h = headers[idx] if idx < len(headers) else f"COL_{idx}"
            row_dict[h] = c
        data[year_key] = row_dict
    return data


def cross_verify_applied_admitted(timeout: int = 45) -> Dict[str, Any]:
    report_info = COMMON_REPORTS[0]
    result: Dict[str, Any] = {
        "id": report_info["id"],
        "title": report_info["title"],
        "category": report_info["category"],
        "status": "HEALTHY",
        "factbook_url": report_info["factbook_url"],
        "trends_url": report_info["trends_url"],
        "total_cells_verified": 0,
        "matching_cells_count": 0,
        "discrepancies": [],
        "comparisons": []
    }

    s_tr = get_fresh_session()
    s_fb = get_fresh_session()

    # Step 1: Query Trends for TTU and MC
    trends_data_by_college: Dict[str, Dict[str, Dict[str, str]]] = {}
    r_tr_init = robust_fetch(s_tr, "GET", report_info["trends_url"], timeout=timeout)
    if not r_tr_init:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "TRENDS_INIT", "message": "Failed to connect to Trends page"})
        return result

    soup_tr = BeautifulSoup(r_tr_init.text, "lxml")
    tr_state = extract_aspnet_state(soup_tr)

    # Initial load is TTU overall (Fall)
    trends_data_by_college["TTU"] = parse_trends_gridview(soup_tr)

    # Postback for MC College
    post_mc = {
        "__EVENTTARGET": "APPADMDropDownList2",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": tr_state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": tr_state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": tr_state.get("__EVENTVALIDATION", ""),
        "APPADMDropDownList1": "27",  # Fall
        "APPADMDropDownList2": "MC"
    }
    r_tr_mc = robust_fetch(s_tr, "POST", report_info["trends_url"], data=post_mc, timeout=timeout)
    if r_tr_mc:
        trends_data_by_college["MC"] = parse_trends_gridview(BeautifulSoup(r_tr_mc.text, "lxml"))

    # Step 2: Query FactBook for matching Fall terms
    r_fb_init = robust_fetch(s_fb, "GET", report_info["factbook_url"], timeout=timeout)
    if not r_fb_init:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "FACTBOOK_INIT", "message": "Failed to connect to FactBook page"})
        return result

    soup_fb = BeautifulSoup(r_fb_init.text, "lxml")
    fb_state = extract_aspnet_state(soup_fb)

    for item in report_info["terms_to_compare"]:
        year = item["year"]
        term_code = item["fb_term_code"]
        term_label = item["fb_term_label"]

        post_fb = {
            "__EVENTTARGET": "ENRDropDownList",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": fb_state.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": fb_state.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": fb_state.get("__EVENTVALIDATION", ""),
            "ENRDropDownList": term_code
        }
        r_term = robust_fetch(s_fb, "POST", report_info["factbook_url"], data=post_fb, timeout=timeout)
        if not r_term:
            continue
        sp_term = BeautifulSoup(r_term.text, "lxml")
        fb_state = extract_aspnet_state(sp_term) or fb_state
        fb_grid = parse_factbook_gridview(sp_term)

        # Check TTU Overall
        if "TOTAL" in fb_grid and "TTU" in trends_data_by_college and year in trends_data_by_college["TTU"]:
            fb_row = fb_grid["TOTAL"]
            tr_row = trends_data_by_college["TTU"][year]
            
            fb_app = fb_row.get("APPLIED", "").replace(",", "")
            tr_app = tr_row.get("Total Applied", "").replace(",", "")
            fb_adm = fb_row.get("ADMITTED", "").replace(",", "")
            tr_adm = tr_row.get("Total Admitted", "").replace(",", "")

            match_app = fb_app == tr_app if (fb_app and tr_app) else False
            match_adm = fb_adm == tr_adm if (fb_adm and tr_adm) else False

            result["total_cells_verified"] += 2
            if match_app: result["matching_cells_count"] += 1
            if match_adm: result["matching_cells_count"] += 1

            cmp_entry = {
                "year": year,
                "term_label": term_label,
                "college": "TTU (Overall)",
                "fb_applied": fb_app,
                "tr_applied": tr_app,
                "applied_match": match_app,
                "fb_admitted": fb_adm,
                "tr_admitted": tr_adm,
                "admitted_match": match_adm,
                "status": "PASS" if (match_app and match_adm) else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

            if not (match_app and match_adm):
                result["status"] = "FAULT"
                result["discrepancies"].append({
                    "component": f"TTU_{year}",
                    "message": f"Applied/Admitted mismatch for TTU {year}: FB Applied={fb_app} vs TR Applied={tr_app}; FB Admitted={fb_adm} vs TR Admitted={tr_adm}"
                })

        # Check MC College
        if "MC" in fb_grid and "MC" in trends_data_by_college and year in trends_data_by_college["MC"]:
            fb_row = fb_grid["MC"]
            tr_row = trends_data_by_college["MC"][year]

            fb_app = fb_row.get("APPLIED", "").replace(",", "")
            tr_app = tr_row.get("Total Applied", "").replace(",", "")
            fb_adm = fb_row.get("ADMITTED", "").replace(",", "")
            tr_adm = tr_row.get("Total Admitted", "").replace(",", "")

            match_app = fb_app == tr_app if (fb_app and tr_app) else False
            match_adm = fb_adm == tr_adm if (fb_adm and tr_adm) else False

            result["total_cells_verified"] += 2
            if match_app: result["matching_cells_count"] += 1
            if match_adm: result["matching_cells_count"] += 1

            cmp_entry = {
                "year": year,
                "term_label": term_label,
                "college": "MC (College of Media & Communication)",
                "fb_applied": fb_app,
                "tr_applied": tr_app,
                "applied_match": match_app,
                "fb_admitted": fb_adm,
                "tr_admitted": tr_adm,
                "admitted_match": match_adm,
                "status": "PASS" if (match_app and match_adm) else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

            if not (match_app and match_adm):
                result["status"] = "FAULT"
                result["discrepancies"].append({
                    "component": f"MC_{year}",
                    "message": f"Applied/Admitted mismatch for MC {year}: FB Applied={fb_app} vs TR Applied={tr_app}; FB Admitted={fb_adm} vs TR Admitted={tr_adm}"
                })

    return result


def cross_verify_degrees(timeout: int = 45) -> Dict[str, Any]:
    report_info = COMMON_REPORTS[1]
    result: Dict[str, Any] = {
        "id": report_info["id"],
        "title": report_info["title"],
        "category": report_info["category"],
        "status": "HEALTHY",
        "factbook_url": report_info["factbook_url"],
        "trends_url": report_info["trends_url"],
        "total_cells_verified": 0,
        "matching_cells_count": 0,
        "discrepancies": [],
        "comparisons": []
    }

    s_tr = get_fresh_session()
    s_fb = get_fresh_session()

    r_tr = robust_fetch(s_tr, "GET", report_info["trends_url"], timeout=timeout)
    if not r_tr:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "TRENDS_INIT", "message": "Failed to connect to Trends Degrees page"})
        return result

    soup_tr = BeautifulSoup(r_tr.text, "lxml")
    tr_state = extract_aspnet_state(soup_tr)

    # Postback for MC
    post_mc = {
        "__EVENTTARGET": "APPADMDropDownList2",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": tr_state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": tr_state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": tr_state.get("__EVENTVALIDATION", ""),
        "APPADMDropDownList1": "FY",
        "APPADMDropDownList2": "MC"
    }
    r_tr_mc = robust_fetch(s_tr, "POST", report_info["trends_url"], data=post_mc, timeout=timeout)
    tr_mc_data = parse_trends_gridview(BeautifulSoup(r_tr_mc.text, "lxml")) if r_tr_mc else {}

    r_fb = robust_fetch(s_fb, "GET", report_info["factbook_url"], timeout=timeout)
    if not r_fb:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "FACTBOOK_INIT", "message": "Failed to connect to FactBook Degrees page"})
        return result

    soup_fb = BeautifulSoup(r_fb.text, "lxml")
    fb_state = extract_aspnet_state(soup_fb)

    for item in report_info["terms_to_compare"]:
        fy_year = item["tr_year"]
        term_code = item["fb_term_code"]
        term_label = item["fb_term_label"]

        post_fb = {
            "__EVENTTARGET": "ENRDropDownList",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": fb_state.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": fb_state.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": fb_state.get("__EVENTVALIDATION", ""),
            "ENRDropDownList": term_code
        }
        r_term = robust_fetch(s_fb, "POST", report_info["factbook_url"], data=post_fb, timeout=timeout)
        if not r_term:
            continue
        sp_term = BeautifulSoup(r_term.text, "lxml")
        fb_state = extract_aspnet_state(sp_term) or fb_state
        fb_grid = parse_factbook_gridview(sp_term)

        if "MC" in fb_grid and fy_year in tr_mc_data:
            fb_row = fb_grid["MC"]
            tr_row = tr_mc_data[fy_year]

            fb_bach = fb_row.get("BACHELORS", "").replace(",", "")
            tr_bach = tr_row.get("Bachelors", "").replace(",", "")
            fb_mast = fb_row.get("MASTERS", "").replace(",", "")
            tr_mast = tr_row.get("Masters", "").replace(",", "")
            fb_doc = fb_row.get("DOCTORAL", "").replace(",", "")
            tr_doc = tr_row.get("Doctoral", "").replace(",", "")
            fb_tot = fb_row.get("TOTAL", "").replace(",", "")
            tr_tot = tr_row.get("Total", "").replace(",", "")

            m_b = fb_bach == tr_bach
            m_m = fb_mast == tr_mast
            m_d = fb_doc == tr_doc
            m_t = fb_tot == tr_tot

            result["total_cells_verified"] += 4
            for m in (m_b, m_m, m_d, m_t):
                if m: result["matching_cells_count"] += 1

            all_match = all([m_b, m_m, m_d, m_t])
            cmp_entry = {
                "year": fy_year,
                "term_label": term_label,
                "college": "MC (College of Media & Communication)",
                "fb_bachelors": fb_bach,
                "tr_bachelors": tr_bach,
                "fb_masters": fb_mast,
                "tr_masters": tr_mast,
                "fb_doctoral": fb_doc,
                "tr_doctoral": tr_doc,
                "fb_total": fb_tot,
                "tr_total": tr_tot,
                "status": "PASS" if all_match else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

            if not all_match:
                result["status"] = "FAULT"
                result["discrepancies"].append({
                    "component": f"DEGREES_MC_{fy_year}",
                    "message": f"Degrees Conferred mismatch for MC {fy_year}: FB Tot={fb_tot} vs TR Tot={tr_tot}"
                })

    return result


def cross_verify_retention(timeout: int = 45) -> Dict[str, Any]:
    report_info = COMMON_REPORTS[2]
    result: Dict[str, Any] = {
        "id": report_info["id"],
        "title": report_info["title"],
        "category": report_info["category"],
        "status": "HEALTHY",
        "factbook_url": report_info["factbook_url"],
        "trends_url": report_info["trends_url"],
        "total_cells_verified": 0,
        "matching_cells_count": 0,
        "discrepancies": [],
        "comparisons": []
    }

    s_tr = get_fresh_session()
    s_fb = get_fresh_session()

    # Query Trends for TTU and MC
    r_tr = robust_fetch(s_tr, "GET", report_info["trends_url"], timeout=timeout)
    if not r_tr:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "TRENDS_INIT", "message": "Failed to connect to Trends Retention page"})
        return result

    soup_tr = BeautifulSoup(r_tr.text, "lxml")
    tr_state = extract_aspnet_state(soup_tr)

    tr_ttu = parse_trends_gridview(soup_tr)

    post_mc = {
        "__EVENTTARGET": "APPADMDropDownList2",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": tr_state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": tr_state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": tr_state.get("__EVENTVALIDATION", ""),
        "APPADMDropDownList2": "MC"
    }
    r_tr_mc = robust_fetch(s_tr, "POST", report_info["trends_url"], data=post_mc, timeout=timeout)
    tr_mc = parse_trends_gridview(BeautifulSoup(r_tr_mc.text, "lxml")) if r_tr_mc else {}

    # Query FactBook for matching Fall cohorts
    r_fb = robust_fetch(s_fb, "GET", report_info["factbook_url"], timeout=timeout)
    if not r_fb:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "FACTBOOK_INIT", "message": "Failed to connect to FactBook Retention page"})
        return result

    soup_fb = BeautifulSoup(r_fb.text, "lxml")
    fb_state = extract_aspnet_state(soup_fb)

    for item in report_info["terms_to_compare"]:
        cohort_year = item["tr_year"]
        term_code = item["fb_term_code"]
        term_label = item["fb_term_label"]

        # Preserve checkboxes so cohort matches Trends default
        post_fb = {
            "__EVENTTARGET": "ENRDropDownList",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": fb_state.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": fb_state.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": fb_state.get("__EVENTVALIDATION", ""),
            "ENRDropDownList": term_code,
            "transferIndicator": "on",
            "ForeignIndicator": "on"
        }
        r_term = robust_fetch(s_fb, "POST", report_info["factbook_url"], data=post_fb, timeout=timeout)
        if not r_term:
            continue
        sp_term = BeautifulSoup(r_term.text, "lxml")
        fb_state = extract_aspnet_state(sp_term) or fb_state
        fb_grid = parse_factbook_gridview(sp_term)

        # Check TTU Overall
        if "TOTAL" in fb_grid and cohort_year in tr_ttu:
            fb_row = fb_grid["TOTAL"]
            tr_row = tr_ttu[cohort_year]

            fb_coh = fb_row.get("COHORT", "").replace(",", "")
            tr_coh = tr_row.get("Cohort*", "").replace(",", "")
            fb_ret = fb_row.get("TOTAL RETAINED", "").replace(",", "")
            tr_ret = tr_row.get("Total Retained in 1-Yr", "").replace(",", "")
            fb_pct = fb_row.get("% RETAINED", "").replace("%", "").strip()
            tr_pct = tr_row.get("% Retained in 1-Yr", "").replace("%", "").strip()

            m_c = fb_coh == tr_coh
            m_r = fb_ret == tr_ret
            m_p = fb_pct == tr_pct

            result["total_cells_verified"] += 3
            for m in (m_c, m_r, m_p):
                if m: result["matching_cells_count"] += 1

            all_match = all([m_c, m_r, m_p])
            cmp_entry = {
                "year": cohort_year,
                "term_label": term_label,
                "college": "TTU (Overall)",
                "fb_cohort": fb_coh,
                "tr_cohort": tr_coh,
                "fb_retained": fb_ret,
                "tr_retained": tr_ret,
                "fb_pct": fb_pct,
                "tr_pct": tr_pct,
                "status": "PASS" if all_match else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

        # Check MC College
        if "MC" in fb_grid and cohort_year in tr_mc:
            fb_row = fb_grid["MC"]
            tr_row = tr_mc[cohort_year]

            fb_coh = fb_row.get("COHORT", "").replace(",", "")
            tr_coh = tr_row.get("Cohort*", "").replace(",", "")
            fb_ret = fb_row.get("TOTAL RETAINED", "").replace(",", "")
            tr_ret = tr_row.get("Total Retained in 1-Yr", "").replace(",", "")
            fb_pct = fb_row.get("% RETAINED", "").replace("%", "").strip()
            tr_pct = tr_row.get("% Retained in 1-Yr", "").replace("%", "").strip()

            m_c = fb_coh == tr_coh
            m_r = fb_ret == tr_ret
            m_p = fb_pct == tr_pct

            result["total_cells_verified"] += 3
            for m in (m_c, m_r, m_p):
                if m: result["matching_cells_count"] += 1

            all_match = all([m_c, m_r, m_p])
            cmp_entry = {
                "year": cohort_year,
                "term_label": term_label,
                "college": "MC (College of Media & Communication)",
                "fb_cohort": fb_coh,
                "tr_cohort": tr_coh,
                "fb_retained": fb_ret,
                "tr_retained": tr_ret,
                "fb_pct": fb_pct,
                "tr_pct": tr_pct,
                "status": "PASS" if all_match else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

    return result


def cross_verify_graduation(timeout: int = 45) -> Dict[str, Any]:
    report_info = COMMON_REPORTS[3]
    result: Dict[str, Any] = {
        "id": report_info["id"],
        "title": report_info["title"],
        "category": report_info["category"],
        "status": "HEALTHY",
        "factbook_url": report_info["factbook_url"],
        "trends_url": report_info["trends_url"],
        "total_cells_verified": 0,
        "matching_cells_count": 0,
        "discrepancies": [],
        "comparisons": []
    }

    s_tr = get_fresh_session()
    s_fb = get_fresh_session()

    # Trends query for TTU and MC
    r_tr = robust_fetch(s_tr, "GET", report_info["trends_url"], timeout=timeout)
    if not r_tr:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "TRENDS_INIT", "message": "Failed to connect to Trends Graduation page"})
        return result

    soup_tr = BeautifulSoup(r_tr.text, "lxml")
    tr_state = extract_aspnet_state(soup_tr)
    tr_ttu = parse_trends_gridview(soup_tr)

    post_mc = {
        "__EVENTTARGET": "APPADMDropDownList2",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": tr_state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": tr_state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": tr_state.get("__EVENTVALIDATION", ""),
        "APPADMDropDownList2": "MC"
    }
    r_tr_mc = robust_fetch(s_tr, "POST", report_info["trends_url"], data=post_mc, timeout=timeout)
    tr_mc = parse_trends_gridview(BeautifulSoup(r_tr_mc.text, "lxml")) if r_tr_mc else {}

    # FactBook query for matching entering Fall terms
    r_fb = robust_fetch(s_fb, "GET", report_info["factbook_url"], timeout=timeout)
    if not r_fb:
        result["status"] = "WARNING"
        result["discrepancies"].append({"component": "FACTBOOK_INIT", "message": "Failed to connect to FactBook Graduation page"})
        return result

    soup_fb = BeautifulSoup(r_fb.text, "lxml")
    fb_state = extract_aspnet_state(soup_fb)

    for item in report_info["terms_to_compare"]:
        cohort_year = item["tr_year"]
        term_code = item["fb_term_code"]
        term_label = item["fb_term_label"]

        post_fb = {
            "__EVENTTARGET": "ENRDropDownList",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": fb_state.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR": fb_state.get("__VIEWSTATEGENERATOR", ""),
            "__EVENTVALIDATION": fb_state.get("__EVENTVALIDATION", ""),
            "ENRDropDownList": term_code,
            "transferIndicator": "on",
            "ForeignIndicator": "on"
        }
        r_term = robust_fetch(s_fb, "POST", report_info["factbook_url"], data=post_fb, timeout=timeout)
        if not r_term:
            continue
        sp_term = BeautifulSoup(r_term.text, "lxml")
        fb_state = extract_aspnet_state(sp_term) or fb_state
        fb_grid = parse_factbook_gridview(sp_term)

        # Check TTU Overall
        if "TOTAL" in fb_grid and cohort_year in tr_ttu:
            fb_row = fb_grid["TOTAL"]
            tr_row = tr_ttu[cohort_year]

            fb_coh = fb_row.get("COHORT", "").replace(",", "")
            tr_coh = tr_row.get("Cohort*", "").replace(",", "")
            fb_grad = fb_row.get("TOTAL GRADUATED", "").replace(",", "")
            tr_grad = tr_row.get("Total Graduated in 4-Yrs", "").replace(",", "")
            fb_pct = fb_row.get("% GRADUATED", "").replace("%", "").strip()
            tr_pct = tr_row.get("% Graduated in 4-Yrs", "").replace("%", "").strip()

            m_c = fb_coh == tr_coh
            m_g = fb_grad == tr_grad
            m_p = fb_pct == tr_pct

            result["total_cells_verified"] += 3
            for m in (m_c, m_g, m_p):
                if m: result["matching_cells_count"] += 1

            all_match = all([m_c, m_g, m_p])
            cmp_entry = {
                "year": cohort_year,
                "term_label": term_label,
                "college": "TTU (Overall)",
                "fb_cohort": fb_coh,
                "tr_cohort": tr_coh,
                "fb_graduated": fb_grad,
                "tr_graduated": tr_grad,
                "fb_pct": fb_pct,
                "tr_pct": tr_pct,
                "status": "PASS" if all_match else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

        # Check MC College
        if "MC" in fb_grid and cohort_year in tr_mc:
            fb_row = fb_grid["MC"]
            tr_row = tr_mc[cohort_year]

            fb_coh = fb_row.get("COHORT", "").replace(",", "")
            tr_coh = tr_row.get("Cohort*", "").replace(",", "")
            fb_grad = fb_row.get("TOTAL GRADUATED", "").replace(",", "")
            tr_grad = tr_row.get("Total Graduated in 4-Yrs", "").replace(",", "")
            fb_pct = fb_row.get("% GRADUATED", "").replace("%", "").strip()
            tr_pct = tr_row.get("% Graduated in 4-Yrs", "").replace("%", "").strip()

            m_c = fb_coh == tr_coh
            m_g = fb_grad == tr_grad
            m_p = fb_pct == tr_pct

            result["total_cells_verified"] += 3
            for m in (m_c, m_g, m_p):
                if m: result["matching_cells_count"] += 1

            all_match = all([m_c, m_g, m_p])
            cmp_entry = {
                "year": cohort_year,
                "term_label": term_label,
                "college": "MC (College of Media & Communication)",
                "fb_cohort": fb_coh,
                "tr_cohort": tr_coh,
                "fb_graduated": fb_grad,
                "tr_graduated": tr_grad,
                "fb_pct": fb_pct,
                "tr_pct": tr_pct,
                "status": "PASS" if all_match else "MISMATCH"
            }
            result["comparisons"].append(cmp_entry)

    return result


def run_common_cross_suite(timeout: int = 45) -> Dict[str, Any]:
    """
    Executes cross-verification across all common reports.
    """
    t0 = time.time()
    results = []
    
    # 1. Applied & Admitted First-Year
    try:
        r1 = cross_verify_applied_admitted(timeout=timeout)
        results.append(r1)
    except Exception as e:
        results.append({
            "id": "applied_admitted_nfr",
            "title": "Applied & Admitted - New First-Year Students",
            "status": "WARNING",
            "discrepancies": [{"component": "CRASH", "message": str(e)}],
            "comparisons": []
        })

    # 2. Degrees Conferred
    try:
        r2 = cross_verify_degrees(timeout=timeout)
        results.append(r2)
    except Exception as e:
        results.append({
            "id": "degrees_conferred",
            "title": "Degrees Conferred - By Level & College",
            "status": "WARNING",
            "discrepancies": [{"component": "CRASH", "message": str(e)}],
            "comparisons": []
        })

    # 3. 1-Year Retention
    try:
        r3 = cross_verify_retention(timeout=timeout)
        results.append(r3)
    except Exception as e:
        results.append({
            "id": "retention_rates_1yr",
            "title": "Retention Rates - 1-Year Cohort Retention",
            "status": "WARNING",
            "discrepancies": [{"component": "CRASH", "message": str(e)}],
            "comparisons": []
        })

    # 4. 4-Year Graduation
    try:
        r4 = cross_verify_graduation(timeout=timeout)
        results.append(r4)
    except Exception as e:
        results.append({
            "id": "graduation_rates_4yr",
            "title": "Graduation Rates - 4-Year College Rates",
            "status": "WARNING",
            "discrepancies": [{"component": "CRASH", "message": str(e)}],
            "comparisons": []
        })

    total_cells = sum(r.get("total_cells_verified", 0) for r in results)
    matching_cells = sum(r.get("matching_cells_count", 0) for r in results)
    total_discrepancies = sum(len(r.get("discrepancies", [])) for r in results)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_sec": round(time.time() - t0, 2),
        "total_common_reports": len(results),
        "total_cells_verified": total_cells,
        "matching_cells_count": matching_cells,
        "match_percentage": round((matching_cells / total_cells * 100), 1) if total_cells > 0 else 100.0,
        "total_discrepancies": total_discrepancies,
        "status": "HEALTHY" if total_discrepancies == 0 else "FAULT",
        "reports": results
    }

    # Save to disk
    out_file = REPORTS_DIR / "common_cross_audit_data.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    rep = run_common_cross_suite(timeout=45)
    print("Cross Verification Report Complete:")
    print(f"Total cells verified: {rep['total_cells_verified']}")
    print(f"Matching cells: {rep['matching_cells_count']} ({rep['match_percentage']}%)")
    print(f"Discrepancies: {rep['total_discrepancies']}")
