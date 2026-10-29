"""
Parser module for TTU FactBook ASP.NET WebForms pages.
Extracts tables, headers, dropdowns, MC data rows, and totals.
"""

import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from config import MC_COLLEGE_CODES, MC_COLLEGE_NAMES, MC_DEPARTMENT_CODES, MC_PROGRAM_PREFIXES


def clean_text(text: Optional[str]) -> str:
    """Clean text by stripping whitespace and non-breaking spaces."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_numeric(val: Any) -> Optional[float]:
    """Parse integer or float from formatted string (e.g., '1,753', '45.2%', '$100')."""
    if val is None:
        return None
    s = clean_text(str(val)).replace(",", "").replace("$", "").replace("%", "")
    if s == "":
        return None
    if s == "-" or s == ".":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def is_mc_row(row_cells: List[str]) -> bool:
    """Determine if a table row corresponds to MC college, department, or program."""
    if not row_cells:
        return False
    row_text = " ".join(row_cells).upper()
    
    # Check college code
    for code in MC_COLLEGE_CODES:
        if any(cell.strip().upper() == code for cell in row_cells[:3]):
            return True
            
    # Check department code
    for dept in MC_DEPARTMENT_CODES:
        if any(cell.strip().upper() == dept for cell in row_cells[:4]):
            return True
            
    # Check program prefix
    for prefix in MC_PROGRAM_PREFIXES:
        if prefix.upper() in row_text:
            return True
            
    # Check college names
    for name in MC_COLLEGE_NAMES:
        if name.upper() in row_text:
            return True
            
    if "MEDIA AND COMMUNICATION" in row_text or "MEDIA & COMMUNICATION" in row_text:
        return True
        
    return False


def parse_factbook_page(html: str, url: str, status_code: int = 200) -> Dict[str, Any]:
    """
    Parse an ASP.NET FactBook HTML page into structured data.
    """
    result: Dict[str, Any] = {
        "url": url,
        "status_code": status_code,
        "is_ok": status_code == 200,
        "error": None,
        "title": "",
        "caption": "",
        "dropdown_terms": [],
        "selected_term": None,
        "export_excel": False,
        "export_pdf": False,
        "headers": [],
        "mc_rows": [],
        "mc_total_row": None,
        "grand_total_row": None,
        "all_rows": [],
        "total_rows_parsed": 0,
    }

    if status_code != 200:
        result["error"] = f"HTTP Error {status_code}"
        return result

    if not html or not html.strip():
        result["error"] = "Empty response received"
        result["is_ok"] = False
        return result

    # Check for ASP.NET runtime error
    if "Server Error in '/' Application" in html or "Runtime Error" in html or "IIS 10.0 Detailed Error" in html:
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        err_title = match.group(1).strip() if match else "ASP.NET / IIS Server Error"
        result["error"] = f"Server Error: {err_title}"
        result["is_ok"] = False
        return result

    soup = BeautifulSoup(html, "lxml")

    # Title & Caption
    title_tag = soup.find("title")
    result["title"] = clean_text(title_tag.string) if title_tag and title_tag.string else ""

    caption_tag = soup.find(id=re.compile(r"caption", re.IGNORECASE))
    if caption_tag:
        result["caption"] = clean_text(caption_tag.get_text())

    # Dropdowns & functionality
    select_tag = soup.find("select", id=re.compile(r"(DropDownList|Term|Year)", re.IGNORECASE))
    if select_tag:
        options = select_tag.find_all("option")
        for opt in options:
            val = opt.get("value", "")
            lbl = clean_text(opt.get_text())
            result["dropdown_terms"].append({"value": val, "label": lbl})
            if opt.get("selected") is not None:
                result["selected_term"] = {"value": val, "label": lbl}

    # Export buttons
    result["export_excel"] = bool(soup.find(id=re.compile(r"excel", re.IGNORECASE)))
    result["export_pdf"] = bool(soup.find(id=re.compile(r"(word|pdf)", re.IGNORECASE)))

    # Locate main data grid table
    grid = soup.find("table", id=re.compile(r"(MyGridView|GridView|grid)", re.IGNORECASE))
    if not grid:
        # Fallback: find any table with width=800 or class divGrid or table with most rows
        tables = soup.find_all("table")
        if tables:
            grid = max(tables, key=lambda t: len(t.find_all("tr")))

    if not grid:
        result["error"] = "No data table found on page"
        return result

    rows = grid.find_all("tr")
    if not rows:
        result["error"] = "Table contains no rows"
        return result

    # Extract headers
    header_rows = [tr for tr in rows if tr.find("th")]
    if header_rows:
        # Combine multi-line headers if needed
        headers = []
        for th in header_rows[-1].find_all(["th", "td"]):
            headers.append(clean_text(th.get_text()))
        result["headers"] = headers
    else:
        # First row as header
        result["headers"] = [clean_text(td.get_text()) for td in rows[0].find_all(["th", "td"])]
        rows = rows[1:]

    # Parse rows
    parsed_rows = []
    for tr in rows:
        cells = [clean_text(td.get_text()) for td in tr.find_all(["th", "td"])]
        if not cells or all(c == "" for c in cells):
            continue

        row_dict = {"raw_cells": cells}
        for idx, cell in enumerate(cells):
            col_name = result["headers"][idx] if idx < len(result["headers"]) else f"COL_{idx}"
            row_dict[col_name] = cell
            num = parse_numeric(cell)
            if num is not None:
                row_dict[f"{col_name}__num"] = num

        parsed_rows.append(row_dict)

        # Check if grand total
        first_few = " ".join(cells[:3]).upper()
        if "TOTAL" in first_few and not any(k in first_few for k in MC_COLLEGE_CODES):
            result["grand_total_row"] = row_dict

        # Check if MC row
        if is_mc_row(cells):
            result["mc_rows"].append(row_dict)
            
            # Check if this row is the college-level MC total row
            # Case 1: College page with single MC row
            # Case 2: Department page with MC row having empty department or "TOTAL"
            c0 = cells[0].strip().upper() if len(cells) > 0 else ""
            c1 = cells[1].strip().upper() if len(cells) > 1 else ""
            c2 = cells[2].strip().upper() if len(cells) > 2 else ""
            if c0 == "MC" and (c1 in ("", "TOTAL") or c2 in ("", "TOTAL") or ("TOTAL" in first_few and c1 == "")):
                # If cells 1 and 2 are empty/blank and subsequent cells are numbers
                result["mc_total_row"] = row_dict
            elif "MC TOTAL" in first_few or "COLLEGE TOTAL" in first_few:
                result["mc_total_row"] = row_dict

    result["all_rows"] = parsed_rows
    result["total_rows_parsed"] = len(parsed_rows)

    # If mc_total_row not explicitly found but only 1 MC row exists, treat it as the total
    if not result["mc_total_row"] and len(result["mc_rows"]) == 1:
        result["mc_total_row"] = result["mc_rows"][0]

    return result


def row_text(cells: List[str]) -> str:
    """Helper to join cells as uppercase."""
    return " ".join(cells).upper()
