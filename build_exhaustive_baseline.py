"""
Script to build comprehensive exhaustive audit dataset across FactBook & Trends.
"""

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from exhaustive_tester import test_factbook_page_exhaustive, test_trends_page_exhaustive, TRENDS_PAGES

target_factbook_pages = [
    {"title": "Applied/Admitted - By College (New First-Year)", "category": "Applied/Admitted", "path": "/FactBook/AppliedAdmitted/APPADMCOLL.aspx?level=nfr"},
    {"title": "Enrollment - By College & Full/Part Time", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRFULLCOLL.aspx"},
    {"title": "Degrees - By Program", "category": "Degrees/Certificates", "path": "/FactBook/Degree/DEGCOLLDEPTPROG.aspx"},
    {"title": "Enrollment - By College", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRCOLL.aspx"},
    {"title": "Enrollment - By Department", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRDEPT.aspx"},
    {"title": "Enrollment - By College & Classification", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRCOLLCLASS.aspx"},
    {"title": "Enrollment - By College & Gender", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRCOLLSEX.aspx"},
    {"title": "Enrollment - By College & Ethnicity", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRETHCOLL.aspx"},
    {"title": "Degrees - By College", "category": "Degrees/Certificates", "path": "/FactBook/Degree/DEGCOLL.aspx"},
    {"title": "Degrees - By Department", "category": "Degrees/Certificates", "path": "/FactBook/Degree/DEGDEPT.aspx"},
    {"title": "Graduation Rates - By College (4-Year)", "category": "Graduation Rates", "path": "/FactBook/GraduationRates/GRADCOLL.aspx?level=4yr"},
    {"title": "Retention Rates - By College (1-Year)", "category": "Retention Rates", "path": "/FactBook/Retention/RETCOLL.aspx"},
    {"title": "New Undergraduate Transfers - By College", "category": "New Undergraduate Transfers", "path": "/FactBook/NewTransfer/NEWFIRSTCOLL.aspx?level=coll"},
]

def main():
    print(f"Executing comprehensive baseline audit across {len(target_factbook_pages)} FactBook pages & {len(TRENDS_PAGES)} Trends pages...")
    t0 = time.time()
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_factbook_pages": len(target_factbook_pages),
        "total_trends_pages": len(TRENDS_PAGES),
        "factbook_results": [],
        "trends_results": [],
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

    # 1. FactBook Audit (All terms for each targeted page)
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(test_factbook_page_exhaustive, p, None, 18): p for p in target_factbook_pages}
        for f in as_completed(futs):
            p = futs[f]
            try:
                r = f.result()
                report["factbook_results"].append(r)
                report["summary"]["total_permutations_tested"] += r["permutations_tested"]
                title_txt = r["title"]
                terms_cnt = r["terms_tested_count"]
                perms = r["permutations_tested"]
                fl_cnt = len(r["faults"])
                print(f"FactBook: {title_txt} -> Terms: {terms_cnt}, Permutations: {perms}, Faults: {fl_cnt}")
            except Exception as e:
                p_title = p["title"]
                print(f"Error on {p_title}: {e}")

    # 2. Trends Audit (All 21 pages across terms and colleges)
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(test_trends_page_exhaustive, tp, None, 18): tp for tp in TRENDS_PAGES}
        for f in as_completed(futs):
            tp = futs[f]
            try:
                r = f.result()
                report["trends_results"].append(r)
                report["summary"]["total_permutations_tested"] += r["permutations_tested"]
                title_txt = r["title"]
                combos = len(r["combinations_summary"])
                perms = r["permutations_tested"]
                fl_cnt = len(r["faults"])
                print(f"Trends: {title_txt} -> Combos: {combos}, Permutations: {perms}, Faults: {fl_cnt}")
            except Exception as e:
                tp_title = tp["title"]
                print(f"Error on {tp_title}: {e}")

    fb_res = report["factbook_results"]
    tr_res = report["trends_results"]
    report["summary"]["factbook_healthy"] = sum(1 for r in fb_res if r["status"] == "HEALTHY")
    report["summary"]["factbook_faults"] = len(fb_res) - report["summary"]["factbook_healthy"]
    report["summary"]["trends_healthy"] = sum(1 for r in tr_res if r["status"] == "HEALTHY")
    report["summary"]["trends_faults"] = len(tr_res) - report["summary"]["trends_healthy"]
    report["summary"]["total_faults_detected"] = sum(len(r["faults"]) for r in fb_res) + sum(len(r["faults"]) for r in tr_res)
    report["summary"]["duration_sec"] = round(time.time() - t0, 2)

    out_file = Path("./reports/exhaustive_audit_data.json")
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    dur = report["summary"]["duration_sec"]
    tot_p = report["summary"]["total_permutations_tested"]
    tot_f = report["summary"]["total_faults_detected"]
    print(f"COMPLETE in {dur}s! Total Permutations: {tot_p}, Total Faults: {tot_f}")

if __name__ == "__main__":
    main()
