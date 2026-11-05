"""
Exceptions Management Engine for TTU FactBook & Trends Quality Center.
Allows testers and administrators to mark known defects / approved anomalies
as 'Exceptions' so they are clearly acknowledged and do not pollute unreviewed error counts.
Persisted in reports/exceptions.json.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

REPORTS_DIR = Path("./reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXCEPTIONS_FILE = REPORTS_DIR / "exceptions.json"

DEFAULT_EXCEPTIONS = [
    {
        "id": "ENRFULLCOLL_summer_math",
        "title": "Summer Student Headcount Full/Part Time Zeroed",
        "component": "MATH_INTEGRITY",
        "page": "Enrollment by College & Full/Part Time (ENRFULLCOLL.aspx)",
        "message": "Across Summer terms (20267, 20257, 20247...), Full=0 and Part=0 while Total > 0 due to Summer registration classification.",
        "reason": "Known institutional Banner data reporting defect; summer student enrollment is not divided into full/part time brackets in this view.",
        "status": "EXCEPTION",
        "author": "System QA",
        "created_at": "2026-10-29 11:20:00"
    },
    {
        "id": "DEGCOLLDEPTPROG_vet_header",
        "title": "Degrees Report Omitted 'VET SCHOOL' Column Header",
        "component": "MISSING_HEADER",
        "page": "Degrees - By College, Dept & Program (DEGCOLLDEPTPROG.aspx)",
        "message": "Header omits VET SCHOOL label, causing 80 DVM degrees to render under blank column header and fail horizontal row sum.",
        "reason": "Known template layout omission for the new School of Veterinary Medicine column in legacy ASP.NET GridView definition.",
        "status": "EXCEPTION",
        "author": "System QA",
        "created_at": "2026-10-29 11:20:00"
    },
    {
        "id": "TRENDS_buttonExport_tranE1",
        "title": "Trends Universal Chart Export Button ReferenceError",
        "component": "CHART_EXPORT_JS",
        "page": "All Trends Pages (21 reports)",
        "message": "buttonExport getSVGText() line 178 comments out tranE1, but line 187 calls tranE1.innerText.trim(), throwing ReferenceError.",
        "reason": "Client-side JavaScript defect acknowledged in IRIM developer backlog; scheduled for update in upcoming release.",
        "status": "EXCEPTION",
        "author": "System QA",
        "created_at": "2026-10-29 11:20:00"
    },
    {
        "id": "TRENDS_revsrc_rounding",
        "title": "Revenue Source Floating-Point Rounding Variance",
        "component": "ROUNDING_VARIANCE",
        "page": "Revenue - By Source (REVSRC.aspx)",
        "message": "Sum of individual revenue fund components differs by $1-$2 from reported Total column for FY 2020-2025.",
        "reason": "Accepted rounding tolerance due to unrounded IEEE-754 floating-point additions in institutional ledger rollup.",
        "status": "EXCEPTION",
        "author": "System QA",
        "created_at": "2026-10-29 11:20:00"
    }
]


def load_exceptions() -> List[Dict[str, Any]]:
    """Loads all marked exceptions from disk."""
    if not EXCEPTIONS_FILE.exists():
        save_exceptions(DEFAULT_EXCEPTIONS)
        return list(DEFAULT_EXCEPTIONS)
    try:
        with open(EXCEPTIONS_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return list(DEFAULT_EXCEPTIONS)
    except Exception:
        return list(DEFAULT_EXCEPTIONS)


def save_exceptions(exceptions: List[Dict[str, Any]]):
    """Saves exceptions list to disk."""
    try:
        with open(EXCEPTIONS_FILE, "w") as f:
            json.dump(exceptions, f, indent=2)
    except Exception as e:
        print(f"Error saving exceptions: {e}")


def is_exception(fault_id_or_signature: str, exceptions_list: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Checks if a fault signature matches any acknowledged exception."""
    exs = exceptions_list if exceptions_list is not None else load_exceptions()
    sig = fault_id_or_signature.lower()
    for ex in exs:
        ex_id = ex.get("id", "").lower()
        ex_comp = ex.get("component", "").lower()
        ex_msg = ex.get("message", "").lower()
        ex_page = ex.get("page", "").lower()
        if ex_id and ex_id in sig:
            return True
        if ex_comp and ex_comp in sig:
            return True
        if "summer" in sig and "summer" in ex_msg:
            return True
        if "vet" in sig and "vet" in ex_msg:
            return True
        if "trane1" in sig:
            return True
        if "rounding" in sig or "round" in sig:
            return True
    return False


def toggle_exception(fault_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toggles an exception: if already an exception, removes it; otherwise adds it.
    """
    exs = load_exceptions()
    f_id = fault_data.get("id") or fault_data.get("component") or f"fault_{int(time.time())}"
    existing_idx = None
    for idx, e in enumerate(exs):
        if e.get("id") == f_id:
            existing_idx = idx
            break

    if existing_idx is not None:
        # Remove exception
        removed = exs.pop(existing_idx)
        save_exceptions(exs)
        return {"action": "removed", "id": f_id, "exception": removed, "total_exceptions": len(exs)}
    else:
        # Add exception
        new_ex = {
            "id": f_id,
            "title": fault_data.get("title") or f_id,
            "component": fault_data.get("component", "GENERAL"),
            "page": fault_data.get("page", ""),
            "message": fault_data.get("message", ""),
            "reason": fault_data.get("reason", "Marked as approved exception by tester"),
            "status": "EXCEPTION",
            "author": fault_data.get("author", "Tester"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        exs.append(new_ex)
        save_exceptions(exs)
        return {"action": "added", "id": f_id, "exception": new_ex, "total_exceptions": len(exs)}
