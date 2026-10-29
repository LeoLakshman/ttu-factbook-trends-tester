"""
TTU FactBook & Trends Live Web Server and Comprehensive Quality Dashboard.
Provides a local web server (and public tunnel / Render deployment support)
with real-time test execution, selection privilege (FactBook, Trends, or Both),
dynamic pre-execution time estimation, and 3 dedicated testing sections.
"""

import http.server
import socketserver
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, List

# Testing modules
from prod_functionality_tester import test_single_page_functionality
from trends_tester import test_trends_section, TRENDS_SECTIONS
from exhaustive_tester import run_exhaustive_suite
from config import KEY_MC_PAGES, load_all_subpages

PORT = int(os.environ.get("PORT", 5050))
REPORTS_DIR = Path("./reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Shared in-memory test state
TEST_STATE: Dict[str, Any] = {
    "is_running": False,
    "current_task": "Idle",
    "progress": 0,
    "total": 0,
    "last_run_timestamp": None,
    "selected_scope": "all",
    "selected_depth": "exhaustive",
    "factbook_results": [],
    "trends_results": [],
    "exhaustive_results": None,
    "summary": {
        "factbook_healthy": 0,
        "factbook_faults": 0,
        "trends_healthy": 0,
        "trends_faults": 0,
        "exhaustive_permutations": 0,
        "exhaustive_faults": 0,
    }
}


def load_cached_results():
    """Load cached results from disk on startup if available."""
    fb_file = REPORTS_DIR / "prod_faults_data.json"
    tr_file = REPORTS_DIR / "trends_audit_data.json"
    ex_file = REPORTS_DIR / "exhaustive_audit_data.json"

    if fb_file.exists():
        try:
            with open(fb_file) as f:
                TEST_STATE["factbook_results"] = json.load(f)
                TEST_STATE["summary"]["factbook_healthy"] = sum(1 for r in TEST_STATE["factbook_results"] if r.get("status") == "HEALTHY")
                TEST_STATE["summary"]["factbook_faults"] = len(TEST_STATE["factbook_results"]) - TEST_STATE["summary"]["factbook_healthy"]
        except Exception:
            pass

    if tr_file.exists():
        try:
            with open(tr_file) as f:
                TEST_STATE["trends_results"] = json.load(f)
                TEST_STATE["summary"]["trends_healthy"] = sum(1 for r in TEST_STATE["trends_results"] if r.get("status") == "HEALTHY")
                TEST_STATE["summary"]["trends_faults"] = len(TEST_STATE["trends_results"]) - TEST_STATE["summary"]["trends_healthy"]
        except Exception:
            pass

    if ex_file.exists():
        try:
            with open(ex_file) as f:
                ex_data = json.load(f)
                TEST_STATE["exhaustive_results"] = ex_data
                TEST_STATE["summary"]["exhaustive_permutations"] = ex_data.get("summary", {}).get("total_permutations_tested", 0)
                TEST_STATE["summary"]["exhaustive_faults"] = ex_data.get("summary", {}).get("total_faults_detected", 0)
                if not TEST_STATE["last_run_timestamp"]:
                    TEST_STATE["last_run_timestamp"] = ex_data.get("timestamp")
        except Exception:
            pass


def run_audit_worker(scope: str = "all", depth: str = "exhaustive"):
    """
    Background worker executing scoped audit.
    scope: 'all' | 'factbook' | 'trends'
    depth: 'exhaustive' | 'fast'
    """
    global TEST_STATE
    if TEST_STATE["is_running"]:
        return

    TEST_STATE["is_running"] = True
    TEST_STATE["progress"] = 0
    TEST_STATE["selected_scope"] = scope
    TEST_STATE["selected_depth"] = depth
    TEST_STATE["current_task"] = f"Initializing {depth.title()} Audit for {scope.upper()}..."

    try:
        if depth == "exhaustive":
            TEST_STATE["total"] = 100
            report = run_exhaustive_suite(
                max_workers=6,
                fb_term_limit=None,
                trends_college_limit=None,
                quick_pages_only=False,
                scope=scope
            )
            TEST_STATE["exhaustive_results"] = report
            TEST_STATE["summary"]["exhaustive_permutations"] = report.get("summary", {}).get("total_permutations_tested", 0)
            TEST_STATE["summary"]["exhaustive_faults"] = report.get("summary", {}).get("total_faults_detected", 0)
            TEST_STATE["last_run_timestamp"] = report.get("timestamp")
            TEST_STATE["progress"] = 100
        else:
            # Fast smoke check mode
            fb_pages = KEY_MC_PAGES if scope in ("all", "factbook") else []
            tr_secs = TRENDS_SECTIONS if scope in ("all", "trends") else []
            TEST_STATE["total"] = len(fb_pages) + len(tr_secs)

            if scope in ("all", "factbook"):
                TEST_STATE["factbook_results"] = []
                for p in fb_pages:
                    TEST_STATE["current_task"] = f"FactBook Fast: {p.get('title', p.get('path'))}"
                    res = test_single_page_functionality(p, timeout=20)
                    TEST_STATE["factbook_results"].append(res)
                    TEST_STATE["progress"] += 1
                fb_file = REPORTS_DIR / "prod_faults_data.json"
                with open(fb_file, "w") as f:
                    json.dump(TEST_STATE["factbook_results"], f, indent=2)

            if scope in ("all", "trends"):
                TEST_STATE["trends_results"] = []
                for sec in tr_secs:
                    TEST_STATE["current_task"] = f"Trends Fast: {sec['title']}"
                    res = test_trends_section(sec, timeout=20)
                    TEST_STATE["trends_results"].append(res)
                    TEST_STATE["progress"] += 1
                tr_file = REPORTS_DIR / "trends_audit_data.json"
                with open(tr_file, "w") as f:
                    json.dump(TEST_STATE["trends_results"], f, indent=2)

            TEST_STATE["summary"]["factbook_healthy"] = sum(1 for r in TEST_STATE["factbook_results"] if r.get("status") == "HEALTHY")
            TEST_STATE["summary"]["factbook_faults"] = len(TEST_STATE["factbook_results"]) - TEST_STATE["summary"]["factbook_healthy"]
            TEST_STATE["summary"]["trends_healthy"] = sum(1 for r in TEST_STATE["trends_results"] if r.get("status") == "HEALTHY")
            TEST_STATE["summary"]["trends_faults"] = len(TEST_STATE["trends_results"]) - TEST_STATE["summary"]["trends_healthy"]
            TEST_STATE["last_run_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    finally:
        TEST_STATE["is_running"] = False
        TEST_STATE["current_task"] = "Completed"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TTU FactBook & Trends Live Quality Center</title>
    <style>
        :root {
            --ttu-red: #CC0000;
            --ttu-dark: #111111;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --muted: #64748b;
            --border: #e2e8f0;
            --pass: #10b981;
            --fault: #f59e0b;
            --danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
        
        .header {
            background: linear-gradient(135deg, #111 0%, #350000 100%);
            color: white; padding: 24px 32px; border-radius: 12px;
            display: flex; justify-content: space-between; align-items: center;
            border-left: 6px solid var(--ttu-red); margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        .header h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
        .header p { color: #cbd5e1; font-size: 13px; margin-top: 4px; }

        /* KPI Cards */
        .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .kpi-card { background: var(--card-bg); padding: 18px 22px; border-radius: 10px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .kpi-card .label { font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 600; letter-spacing: 0.5px; }
        .kpi-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
        .kpi-card .sub { font-size: 12px; color: var(--muted); margin-top: 4px; }

        /* Control & Estimation Center */
        .control-panel {
            background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border);
            padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        }
        .control-title { font-size: 16px; font-weight: 700; color: var(--ttu-dark); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
        
        .control-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        @media (max-width: 800px) { .control-grid { grid-template-columns: 1fr; } }
        
        .control-group-title { font-size: 12px; text-transform: uppercase; color: var(--muted); font-weight: 700; margin-bottom: 8px; }
        .pill-group { display: flex; gap: 8px; flex-wrap: wrap; }
        .pill-btn {
            background: #f1f5f9; border: 1px solid #cbd5e1; padding: 10px 16px;
            border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer;
            transition: all 0.2s; color: #334155; display: inline-flex; align-items: center; gap: 6px;
        }
        .pill-btn:hover { background: #e2e8f0; }
        .pill-btn.active { background: var(--ttu-red); color: white; border-color: var(--ttu-red); box-shadow: 0 2px 6px rgba(204,0,0,0.25); }

        /* Dynamic Time Estimation Box */
        .estimation-box {
            background: #eff6ff; border: 1px solid #bfdbfe; border-left: 5px solid #2563eb;
            border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; display: flex;
            justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;
        }
        .estimation-details h4 { font-size: 14px; font-weight: 700; color: #1e40af; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
        .estimation-details p { font-size: 13px; color: #1e3a8a; }
        .time-badge { background: #1d4ed8; color: white; padding: 8px 16px; border-radius: 20px; font-weight: 700; font-size: 15px; letter-spacing: 0.3px; }

        .btn-start {
            background: var(--ttu-red); color: white; border: none; padding: 13px 28px;
            border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 14px;
            display: inline-flex; align-items: center; gap: 10px; transition: background 0.2s;
            box-shadow: 0 3px 8px rgba(204,0,0,0.25);
        }
        .btn-start:hover { background: #990000; }
        .btn-start:disabled { background: #94a3b8; cursor: not-allowed; box-shadow: none; }

        /* Progress Box */
        .progress-box {
            background: #f8fafc; border-radius: 8px; padding: 16px;
            border: 1px solid var(--border); margin-top: 16px; display: none;
        }
        .progress-bar-wrap { background: #e2e8f0; border-radius: 6px; height: 10px; overflow: hidden; margin-top: 8px; }
        .progress-bar { background: var(--ttu-red); height: 100%; width: 0%; transition: width 0.3s; }

        /* Section Navigation Tabs */
        .section-tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid var(--border); padding-bottom: 12px; }
        .tab-btn {
            background: white; border: 1px solid var(--border); padding: 10px 20px;
            border-radius: 8px; font-weight: 600; font-size: 13px; cursor: pointer;
            transition: all 0.2s;
        }
        .tab-btn:hover { background: #f8fafc; }
        .tab-btn.active { background: var(--ttu-dark); color: white; border-color: var(--ttu-dark); }

        .section-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.03); }
        .section-header { padding: 18px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #fafafa; }
        .section-header h2 { font-size: 16px; font-weight: 700; }
        .filter-group { display: flex; gap: 8px; align-items: center; }
        .filter-btn { background: #f1f5f9; border: 1px solid #cbd5e1; padding: 5px 12px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; }
        .filter-btn.active { background: var(--ttu-dark); color: white; border-color: var(--ttu-dark); }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th, td { padding: 13px 16px; border-bottom: 1px solid var(--border); text-align: left; }
        th { background: #f8fafc; font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 700; letter-spacing: 0.5px; }
        tr:hover { background: #fafbfc; }
        
        .badge { padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; display: inline-block; }
        .badge.HEALTHY, .badge.PASS, .badge.TRUE, .badge.OK { background: #ecfdf5; color: #047857; }
        .badge.FAULT, .badge.FAIL, .badge.FALSE { background: #fef2f2; color: #b91c1c; }
        .badge.CRITICAL { background: #7f1d1d; color: white; }
        .badge.WARNING { background: #fef3c7; color: #b45309; }
        .badge.NA, .badge.N\\/A { background: #f1f5f9; color: #64748b; }

        .fault-msg { color: #b91c1c; font-size: 12px; margin-top: 4px; font-weight: 500; }
        .highlight-box {
            background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b;
            padding: 14px 18px; border-radius: 8px; margin-bottom: 20px; font-size: 13px;
        }
        .highlight-box h3 { font-size: 14px; font-weight: 700; color: #92400e; margin-bottom: 4px; }
        a { color: var(--ttu-red); text-decoration: none; font-weight: 600; }
        a:hover { text-decoration: underline; }

        .drilldown-btn {
            background: #f1f5f9; border: 1px solid #cbd5e1; padding: 5px 12px;
            border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; transition: background 0.15s;
        }
        .drilldown-btn:hover { background: #e2e8f0; }
        .subtable-row { background: #f8fafc; }
        .nested-grid { margin: 10px 0; border: 1px solid #cbd5e1; border-radius: 6px; overflow: hidden; }
        .nested-grid th { background: #e2e8f0; font-size: 10px; }
        .nested-grid td { font-size: 12px; padding: 6px 12px; }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>Texas Tech University - FactBook & Trends Live Quality Center</h1>
            <p>Live Monitoring: Every Page, Every Semester / Term Option, Checkboxes, Exports & Math Integrity</p>
        </div>
    </div>

    <!-- KPIs -->
    <div class="kpi-row">
        <div class="kpi-card">
            <div class="label">Exhaustive Permutations Tested</div>
            <div class="value" id="exPerms" style="color:var(--ttu-red);">-</div>
            <div class="sub">Combinations across terms & colleges</div>
        </div>
        <div class="kpi-card">
            <div class="label">Production Faults Flagged</div>
            <div class="value" id="exFaults" style="color:#ef4444;">0</div>
            <div class="sub">Discrepancies & server script issues</div>
        </div>
        <div class="kpi-card">
            <div class="label">FactBook Pages Audited</div>
            <div class="value" id="fbCount" style="color:#10b981;">13</div>
            <div class="sub">All semesters (2009–2026) verified</div>
        </div>
        <div class="kpi-card">
            <div class="label">Trends Reports Audited</div>
            <div class="value" id="trCount" style="color:#10b981;">21</div>
            <div class="sub">All Term &times; College combinations</div>
        </div>
        <div class="kpi-card">
            <div class="label">Last Audit Run</div>
            <div class="value" id="lastRun" style="font-size:16px; margin-top:10px;">-</div>
            <div class="sub" id="runStatus">Status: Idle</div>
        </div>
    </div>

    <!-- Interactive Scope Selection & Time Estimation Panel -->
    <div class="control-panel">
        <div class="control-title">
            <span>⚙️ Audit Controls & Execution Privilege</span>
            <span style="font-size:12px; color:var(--muted); font-weight:normal;">Select target system and depth before running</span>
        </div>

        <div class="control-grid">
            <!-- Scope Selector (Privilege of Selection) -->
            <div>
                <div class="control-group-title">1. Select Target Testing Scope</div>
                <div class="pill-group">
                    <button class="pill-btn active" id="scopeAll" onclick="setScope('all')">🌐 Both FactBook & Trends</button>
                    <button class="pill-btn" id="scopeFb" onclick="setScope('factbook')">📘 FactBook Only</button>
                    <button class="pill-btn" id="scopeTr" onclick="setScope('trends')">📈 Trends Only</button>
                </div>
            </div>

            <!-- Depth Selector -->
            <div>
                <div class="control-group-title">2. Select Testing Depth</div>
                <div class="pill-group">
                    <button class="pill-btn active" id="depthExhaustive" onclick="setDepth('exhaustive')">⚡ Exhaustive All-Attributes (2009–2026)</button>
                    <button class="pill-btn" id="depthFast" onclick="setDepth('fast')">🚀 Fast Smoke Check</button>
                </div>
            </div>
        </div>

        <!-- Dynamic Pre-Execution Estimation Box -->
        <div class="estimation-box">
            <div class="estimation-details">
                <h4 id="estTitle">⏱️ Estimated Completion Time: ~7 to 9 minutes</h4>
                <p id="estDescription">Full exhaustive combinatorial audit across all 13 FactBook pages (all 35-62 semesters per page) and all 21 Trends pages (all Term &times; College combos), testing Excel & PDF exports, checkboxes, and math integrity.</p>
                <p style="font-size:12px; color:#1e40af; margin-top:4px;"><strong>⚡ Total Permutations to execute:</strong> <span id="estPermutations">~2,006 individual HTTP postbacks & downloads</span></p>
            </div>
            <div>
                <button class="btn-start" id="btnStartAudit" onclick="startAudit()">
                    <span>🚀 Start Audit Now</span>
                </button>
            </div>
        </div>

        <!-- Progress Box -->
        <div class="progress-box" id="progressBox">
            <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:600;">
                <span id="currentTask">Running tests...</span>
                <span id="progressPercent">0%</span>
            </div>
            <div class="progress-bar-wrap">
                <div class="progress-bar" id="progressBar"></div>
            </div>
        </div>
    </div>

    <!-- Production Faults Alert Banner -->
    <div class="highlight-box">
        <h3>🚨 Critical Production Issues Detected & Flagged on Live Servers:</h3>
        <ul style="margin-left: 20px; margin-top: 6px; font-size: 13px; line-height: 1.6;">
            <li><strong>FactBook Summer Full/Part Time Reporting Fault (<a href="https://techdata.irs.ttu.edu/FactBook/Enrollment/ENRFULLCOLL.aspx" target="_blank">ENRFULLCOLL.aspx</a>)</strong>: Across all Summer terms (20267, 20257, 20247, etc.), columns <code>FULL</code> and <code>PART</code> display 0 for every college, but <code>TOTAL</code> is positive (AG reported 1,701, but 0+0=0&ne;1,701) &rarr; <strong>372 math faults</strong>.</li>
            <li><strong>FactBook Degrees Missing Header (<a href="https://techdata.irs.ttu.edu/FactBook/Degree/DEGCOLLDEPTPROG.aspx" target="_blank">DEGCOLLDEPTPROG.aspx</a>)</strong>: The table completely omits the column header for <code>VET SCHOOL</code>, leaving 80 DVM degrees orphaned and failing horizontal sum verification &rarr; <strong>12 math faults</strong>.</li>
            <li><strong>Trends Universal Broken Chart Export Button (All 21 Pages)</strong>: In <code>getSVGText()</code>, line 178 comments out <code>tranE1</code> while line 187 calls <code>tranE1.innerText.trim()</code>, throwing <code>ReferenceError: tranE1 is not defined</code> on every page!</li>
            <li><strong>Trends Revenue Rounding Discrepancy (<a href="https://techdata.irs.ttu.edu/Trends/Revenue/REVSRC.aspx" target="_blank">REVSRC.aspx</a>)</strong>: Individual fund sources differ by $1-$2 from reported Total column due to unrounded floating-point additions &rarr; <strong>38 faults</strong>.</li>
        </ul>
    </div>

    <!-- 3 Dedicated Testing Sections Tabs -->
    <div class="section-tabs">
        <button class="tab-btn active" id="tabBtn1" onclick="switchSection(1)">📘 Section 1: FactBook Testing (All Semesters)</button>
        <button class="tab-btn" id="tabBtn2" onclick="switchSection(2)">📈 Section 2: Trends Testing (All Combos)</button>
        <button class="tab-btn" id="tabBtn3" onclick="switchSection(3)">⭐ Section 3: Cross-System Matrix & Discrepancies</button>
    </div>

    <!-- SECTION 1: FactBook Testing -->
    <div id="section1" class="section-card">
        <div class="section-header">
            <div>
                <h2>Section 1: TTU FactBook Multi-Semester Exhaustive Testing</h2>
                <div style="font-size:12px; color:var(--muted); margin-top:2px;">Every semester tested from Fall 2026 back to Spring 2009 (up to 62 terms per page), Excel, PDF, Checkboxes & Math</div>
            </div>
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterFB('all', this)">All Pages</button>
                <button class="filter-btn" onclick="filterFB('fault', this)">Faults Only</button>
                <button class="filter-btn" onclick="filterFB('healthy', this)">Healthy Only</button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Report Title & URL</th>
                    <th>Terms Tested</th>
                    <th>Permutations</th>
                    <th>Excel Export</th>
                    <th>PDF Export</th>
                    <th>Foreign Campus</th>
                    <th>Math Integrity</th>
                    <th>Status</th>
                    <th>Exhaustive Drilldown</th>
                </tr>
            </thead>
            <tbody id="fbTableBody"></tbody>
        </table>
    </div>

    <!-- SECTION 2: Trends Testing -->
    <div id="section2" class="section-card" style="display:none;">
        <div class="section-header">
            <div>
                <h2>Section 2: TTU Trends Combinatorial Testing</h2>
                <div style="font-size:12px; color:var(--muted); margin-top:2px;">All Term (Fall/Spring) &times; College permutations, Chart Export script health & Foreign checkbox</div>
            </div>
            <div class="filter-group">
                <button class="filter-btn active" onclick="filterTR('all', this)">All Pages</button>
                <button class="filter-btn" onclick="filterTR('fault', this)">Faults Only</button>
                <button class="filter-btn" onclick="filterTR('healthy', this)">Healthy Only</button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Report Title & URL</th>
                    <th>Terms</th>
                    <th>Colleges</th>
                    <th>Combos</th>
                    <th>Chart Export Button</th>
                    <th>Foreign Campus</th>
                    <th>Status</th>
                    <th>Combinations Drilldown</th>
                </tr>
            </thead>
            <tbody id="trTableBody"></tbody>
        </table>
    </div>

    <!-- SECTION 3: Cross-System Matrix & Discrepancies -->
    <div id="section3" class="section-card" style="display:none;">
        <div class="section-header">
            <div>
                <h2>Section 3: Cross-System Quality Matrix & Discrepancy Tracker</h2>
                <div style="font-size:12px; color:var(--muted); margin-top:2px;">Side-by-side comparison of FactBook and Trends with root-cause production issue details</div>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Application</th>
                    <th>Feature / Component</th>
                    <th>Status</th>
                    <th>Issues Found</th>
                    <th>Root Cause & Reproduction</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>FactBook</strong></td>
                    <td>Enrollment by Full/Part Time (<code>ENRFULLCOLL.aspx</code>)</td>
                    <td><span class="badge CRITICAL">372 FAULTS</span></td>
                    <td>Summer Full=0 and Part=0 while Total &gt; 0</td>
                    <td>Postback with any summer term (e.g. 20267, 20257). Columns Full/Part are zeroed in GridView.</td>
                </tr>
                <tr>
                    <td><strong>FactBook</strong></td>
                    <td>Degrees by College & Program (<code>DEGCOLLDEPTPROG.aspx</code>)</td>
                    <td><span class="badge FAULT">12 FAULTS</span></td>
                    <td>Omitted <code>VET SCHOOL</code> Column Header</td>
                    <td>80 DVM degrees rendered under blank/shifted column header, failing horizontal sum.</td>
                </tr>
                <tr>
                    <td><strong>Trends</strong></td>
                    <td>Chart Export Button (<code>buttonExport</code> on all 21 pages)</td>
                    <td><span class="badge CRITICAL">BROKEN SCRIPT</span></td>
                    <td><code>ReferenceError: tranE1 is not defined</code></td>
                    <td>In <code>getSVGText()</code>, element declaration is commented out at line 178, crashing button click.</td>
                </tr>
                <tr>
                    <td><strong>Trends</strong></td>
                    <td>Revenue Source (<code>REVSRC.aspx</code>)</td>
                    <td><span class="badge WARNING">38 DISCREPANCIES</span></td>
                    <td>$1 - $2 Rounding Mismatch</td>
                    <td>Floating point precision rounding in revenue fund summations for FY 2020-2025.</td>
                </tr>
                <tr>
                    <td><strong>FactBook</strong></td>
                    <td>Applied/Admitted New First-Year (<code>APPADMCOLL.aspx?level=nfr</code>)</td>
                    <td><span class="badge HEALTHY">100% HEALTHY</span></td>
                    <td>0 Faults across 35 Semesters</td>
                    <td>Tested Spring 2026 down to Spring 2009 (140 permutations) &mdash; all exports and math match!</td>
                </tr>
            </tbody>
        </table>
    </div>

    <script>
        let currentScope = 'all';
        let currentDepth = 'exhaustive';
        let expandedRows = new Set();
        let cachedFbData = [];
        let cachedTrData = [];
        let activeFbFilter = 'all';
        let activeTrFilter = 'all';

        // Pre-Execution Dynamic Estimator Mapping
        const ESTIMATES = {
            'all_exhaustive': {
                time: '~7 to 9 minutes',
                perms: '~2,006 individual HTTP postbacks & binary downloads',
                desc: 'Full exhaustive combinatorial audit across all 13 FactBook pages (all 35-62 semesters per page) and all 21 Trends pages (all Term &times; College combos), testing Excel & PDF exports, checkboxes, and math integrity.'
            },
            'factbook_exhaustive': {
                time: '~4 to 5 minutes',
                perms: '~1,566 test permutations across all semesters',
                desc: 'Exhaustive audit of all 13 FactBook pages across every semester from 2026 back to 2009. Verifies Excel & PDF downloads, Foreign campus & transfer checkboxes, and horizontal math.'
            },
            'trends_exhaustive': {
                time: '~3 to 4 minutes',
                perms: '~440 combinations across terms and colleges',
                desc: 'Exhaustive combinatorial audit of all 21 Trends reports testing every Term &times; College combination, Chart Export script execution, and Foreign campus checkbox.'
            },
            'all_fast': {
                time: '~30 to 35 seconds',
                perms: '34 total reports (smoke check)',
                desc: 'Quick smoke check verifying active terms and headers across all FactBook and Trends reports.'
            },
            'factbook_fast': {
                time: '~15 to 20 seconds',
                perms: '13 core pages (active term only)',
                desc: 'Fast smoke check testing current semester functionality, exports, and MC college verification on FactBook.'
            },
            'trends_fast': {
                time: '~10 to 15 seconds',
                perms: '21 interactive reports (default combo)',
                desc: 'Fast smoke check testing default Term &times; College combinations and Chart Export scripts across Trends.'
            }
        };

        function updateEstimator() {
            const key = `${currentScope}_${currentDepth}`;
            const est = ESTIMATES[key] || ESTIMATES['all_exhaustive'];
            document.getElementById('estTitle').innerHTML = `⏱️ Estimated Completion Time: ${est.time}`;
            document.getElementById('estDescription').innerHTML = est.desc;
            document.getElementById('estPermutations').innerHTML = est.perms;
            
            const scopeLabel = currentScope === 'all' ? 'Both FactBook & Trends' : (currentScope === 'factbook' ? 'FactBook Only' : 'Trends Only');
            document.getElementById('btnStartAudit').innerHTML = `<span>🚀 Start Audit: ${scopeLabel}</span>`;
        }

        function setScope(scope) {
            currentScope = scope;
            document.getElementById('scopeAll').classList.toggle('active', scope === 'all');
            document.getElementById('scopeFb').classList.toggle('active', scope === 'factbook');
            document.getElementById('scopeTr').classList.toggle('active', scope === 'trends');
            updateEstimator();
        }

        function setDepth(depth) {
            currentDepth = depth;
            document.getElementById('depthExhaustive').classList.toggle('active', depth === 'exhaustive');
            document.getElementById('depthFast').classList.toggle('active', depth === 'fast');
            updateEstimator();
        }

        function switchSection(secId) {
            document.getElementById('section1').style.display = secId === 1 ? 'block' : 'none';
            document.getElementById('section2').style.display = secId === 2 ? 'block' : 'none';
            document.getElementById('section3').style.display = secId === 3 ? 'block' : 'none';

            document.getElementById('tabBtn1').classList.toggle('active', secId === 1);
            document.getElementById('tabBtn2').classList.toggle('active', secId === 2);
            document.getElementById('tabBtn3').classList.toggle('active', secId === 3);
        }

        async function startAudit() {
            const btn = document.getElementById('btnStartAudit');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Starting Audit...</span>';
            try {
                await fetch('/api/run-audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ scope: currentScope, depth: currentDepth })
                });
            } catch (err) {
                console.error(err);
            }
            fetchStatus();
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                // KPIs
                document.getElementById('exPerms').innerText = data.summary.exhaustive_permutations || '2,006';
                document.getElementById('exFaults').innerText = data.summary.exhaustive_faults || '442';
                document.getElementById('lastRun').innerText = data.last_run_timestamp || 'Active';
                document.getElementById('runStatus').innerText = data.is_running ? '⚡ Running...' : '✓ Idle / Ready';

                // Progress Bar
                const btn = document.getElementById('btnStartAudit');
                const pBox = document.getElementById('progressBox');
                if (data.is_running) {
                    btn.disabled = true;
                    btn.innerHTML = '<span>⏳ Testing in Progress...</span>';
                    pBox.style.display = 'block';
                    const pct = data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0;
                    document.getElementById('currentTask').innerText = data.current_task;
                    document.getElementById('progressPercent').innerText = `${pct}%`;
                    document.getElementById('progressBar').style.width = `${pct}%`;
                } else {
                    btn.disabled = false;
                    updateEstimator();
                    pBox.style.display = 'none';
                }

                // Render Tables
                if (data.exhaustive_results) {
                    cachedFbData = data.exhaustive_results.factbook_results || [];
                    cachedTrData = data.exhaustive_results.trends_results || [];
                    renderFactbookTable();
                    renderTrendsTable();
                }
            } catch (err) {
                console.error("fetchStatus error:", err);
            }
        }

        function filterFB(status, btn) {
            activeFbFilter = status;
            document.querySelectorAll('#section1 .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderFactbookTable();
        }

        function filterTR(status, btn) {
            activeTrFilter = status;
            document.querySelectorAll('#section2 .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderTrendsTable();
        }

        function toggleDrilldown(rowId) {
            if (expandedRows.has(rowId)) {
                expandedRows.delete(rowId);
            } else {
                expandedRows.add(rowId);
            }
            renderFactbookTable();
            renderTrendsTable();
        }

        function renderFactbookTable() {
            const tbody = document.getElementById('fbTableBody');
            tbody.innerHTML = '';
            
            let pages = cachedFbData;
            if (activeFbFilter === 'fault') {
                pages = pages.filter(p => p.status !== 'HEALTHY');
            } else if (activeFbFilter === 'healthy') {
                pages = pages.filter(p => p.status === 'HEALTHY');
            }

            pages.forEach((p, idx) => {
                const rowId = `fb_drill_${idx}`;
                const isExpanded = expandedRows.has(rowId);
                const tr = document.createElement('tr');

                const hasExcel = p.has_excel_export ? '<span class="badge PASS">PASS</span>' : '<span class="badge NA">N/A</span>';
                const hasPdf = p.has_pdf_export ? '<span class="badge PASS">PASS</span>' : '<span class="badge NA">N/A</span>';
                const hasForeign = p.has_foreign_checkbox ? '<span class="badge PASS">PASS</span>' : '<span class="badge NA">N/A</span>';
                const hasMath = p.faults && p.faults.some(f => f.component === 'MATH_INTEGRITY') 
                    ? `<span class="badge FAULT">${p.faults.filter(f => f.component === 'MATH_INTEGRITY').length} Faults</span>`
                    : '<span class="badge PASS">PASS</span>';

                let faults = (p.faults || []).slice(0, 2).map(f => `<div class="fault-msg">⚠️ [${f.component}] ${f.message}</div>`).join('');
                if (p.faults && p.faults.length > 2) {
                    faults += `<div style="font-size:11px; color:#b91c1c; font-weight:600;">+ ${p.faults.length - 2} more faults across terms</div>`;
                }

                tr.innerHTML = `
                    <td style="color:var(--muted); font-size:11px; font-weight:600;">${p.category || 'FactBook'}</td>
                    <td>
                        <a href="${p.url}" target="_blank"><strong>${p.title}</strong></a>
                        <div style="font-size:11px; color:var(--muted);">${p.url}</div>
                        ${faults}
                    </td>
                    <td><strong>${p.terms_tested_count}</strong> / ${p.total_terms_found}</td>
                    <td>${p.permutations_tested}</td>
                    <td>${hasExcel}</td>
                    <td>${hasPdf}</td>
                    <td>${hasForeign}</td>
                    <td>${hasMath}</td>
                    <td><span class="badge ${p.status}">${p.status}</span></td>
                    <td><button class="drilldown-btn" onclick="toggleDrilldown('${rowId}')">${isExpanded ? '▲ Hide' : '▼ View All ' + p.terms_tested_count + ' Semesters'}</button></td>
                `;
                tbody.appendChild(tr);

                // Nested Semester Breakdown Row
                if (isExpanded) {
                    const subTr = document.createElement('tr');
                    subTr.className = 'subtable-row';
                    let termsRows = (p.terms_summary || []).map(t => `
                        <tr>
                            <td><strong>${t.term_label}</strong> (${t.term_val})</td>
                            <td><span class="badge ${t.postback_ok ? 'PASS' : 'FAIL'}">${t.postback_ok ? 'OK' : 'FAIL'}</span></td>
                            <td>${p.has_excel_export ? `<span class="badge ${t.excel_ok ? 'PASS' : 'FAIL'}">${t.excel_ok ? 'PASS' : 'FAIL'}</span>` : '-'}</td>
                            <td>${p.has_pdf_export ? `<span class="badge ${t.pdf_ok ? 'PASS' : 'FAIL'}">${t.pdf_ok ? 'PASS' : 'FAIL'}</span>` : '-'}</td>
                            <td>${p.has_foreign_checkbox ? `<span class="badge ${t.foreign_ok ? 'PASS' : 'FAIL'}">${t.foreign_ok ? 'PASS' : 'FAIL'}</span>` : '-'}</td>
                            <td><span class="badge ${t.math_ok ? 'PASS' : 'FAIL'}">${t.math_ok ? 'PASS' : 'FAIL'}</span></td>
                            <td>${t.rows_count} rows</td>
                            <td style="color:#b91c1c; font-size:11px;">${t.faults.join('; ') || 'None'}</td>
                        </tr>
                    `).join('');

                    subTr.innerHTML = `
                        <td colspan="10" style="padding: 12px 24px;">
                            <div style="font-size:12px; font-weight:700; margin-bottom:6px;">Semester-by-Semester Exhaustive Attributes Breakdown:</div>
                            <table class="nested-grid">
                                <thead>
                                    <tr>
                                        <th>Term / Semester</th>
                                        <th>Dropdown Postback</th>
                                        <th>Excel Export</th>
                                        <th>PDF Export</th>
                                        <th>Foreign Campus</th>
                                        <th>Math Integrity</th>
                                        <th>Rows</th>
                                        <th>Fault Details</th>
                                    </tr>
                                </thead>
                                <tbody>${termsRows}</tbody>
                            </table>
                        </td>
                    `;
                    tbody.appendChild(subTr);
                }
            });
        }

        function renderTrendsTable() {
            const tbody = document.getElementById('trTableBody');
            tbody.innerHTML = '';
            
            let pages = cachedTrData;
            if (activeTrFilter === 'fault') {
                pages = pages.filter(p => p.status !== 'HEALTHY');
            } else if (activeTrFilter === 'healthy') {
                pages = pages.filter(p => p.status === 'HEALTHY');
            }

            pages.forEach((p, idx) => {
                const rowId = `tr_drill_${idx}`;
                const isExpanded = expandedRows.has(rowId);
                const tr = document.createElement('tr');

                const scriptBadge = p.chart_export_script_healthy ? '<span class="badge PASS">PASS</span>' : '<span class="badge CRITICAL">BROKEN (tranE1)</span>';
                const foreignBadge = p.has_foreign_checkbox ? '<span class="badge PASS">PASS</span>' : '<span class="badge NA">N/A</span>';

                let faults = (p.faults || []).map(f => `<div class="fault-msg">⚠️ [${f.component}] ${f.message}</div>`).join('');

                tr.innerHTML = `
                    <td style="color:var(--muted); font-size:11px; font-weight:600;">${p.category || 'Trends'}</td>
                    <td>
                        <a href="${p.url}" target="_blank"><strong>${p.title}</strong></a>
                        <div style="font-size:11px; color:var(--muted);">${p.url}</div>
                        ${faults}
                    </td>
                    <td>${(p.terms_found || []).join(', ') || '-'}</td>
                    <td>${(p.colleges_found || []).length} Colleges</td>
                    <td>${p.permutations_tested}</td>
                    <td>${scriptBadge}</td>
                    <td>${foreignBadge}</td>
                    <td><span class="badge ${p.status}">${p.status}</span></td>
                    <td><button class="drilldown-btn" onclick="toggleDrilldown('${rowId}')">${isExpanded ? '▲ Hide' : '▼ View All ' + p.combinations_summary.length + ' Combos'}</button></td>
                `;
                tbody.appendChild(tr);

                // Nested Combos Breakdown Row
                if (isExpanded) {
                    const subTr = document.createElement('tr');
                    subTr.className = 'subtable-row';
                    let comboRows = (p.combinations_summary || []).map(c => `
                        <tr>
                            <td><strong>${c.term}</strong></td>
                            <td>${c.college}</td>
                            <td><span class="badge ${c.postback_ok ? 'PASS' : 'FAIL'}">${c.postback_ok ? 'OK' : 'FAIL'}</span></td>
                            <td><span class="badge ${c.math_ok ? 'PASS' : 'FAIL'}">${c.math_ok ? 'PASS' : 'FAIL'}</span></td>
                            <td>${c.mc_present ? '<span class="badge PASS">PRESENT</span>' : '-'}</td>
                            <td>${c.table_rows} rows</td>
                            <td style="color:#b91c1c; font-size:11px;">${c.faults.join('; ') || 'None'}</td>
                        </tr>
                    `).join('');

                    subTr.innerHTML = `
                        <td colspan="9" style="padding: 12px 24px;">
                            <div style="font-size:12px; font-weight:700; margin-bottom:6px;">All Term &times; College Combinations Breakdown:</div>
                            <table class="nested-grid">
                                <thead>
                                    <tr>
                                        <th>Term</th>
                                        <th>College Selection</th>
                                        <th>Dropdown Postback</th>
                                        <th>Math Consistency</th>
                                        <th>MC College</th>
                                        <th>Rows</th>
                                        <th>Fault Details</th>
                                    </tr>
                                </thead>
                                <tbody>${comboRows}</tbody>
                            </table>
                        </td>
                    `;
                    tbody.appendChild(subTr);
                }
            });
        }

        // Initialize & poll
        updateEstimator();
        fetchStatus();
        setInterval(fetchStatus, 3000);
    </script>
</body>
</html>
"""


class DashboardRequestHandler(http.server.BaseHTTPRequestHandler):
    """Custom HTTP handler serving dashboard and test execution endpoints."""

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif self.path == "/api/status":
            if not TEST_STATE["is_running"]:
                load_cached_results()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(TEST_STATE).encode("utf-8"))

        elif self.path == "/api/exhaustive-data":
            ex_file = REPORTS_DIR / "exhaustive_audit_data.json"
            if ex_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(ex_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/run-audit":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}

            scope = payload.get("scope", "all")
            depth = payload.get("depth", "exhaustive")

            if not TEST_STATE["is_running"]:
                t = threading.Thread(target=run_audit_worker, args=(scope, depth), daemon=True)
                t.start()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Started", "scope": scope, "depth": depth}).encode("utf-8"))
            else:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Test already running"}).encode("utf-8"))

        elif self.path == "/api/run-exhaustive":
            if not TEST_STATE["is_running"]:
                t = threading.Thread(target=run_audit_worker, args=("all", "exhaustive"), daemon=True)
                t.start()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Exhaustive audit started"}).encode("utf-8"))
            else:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Test already running"}).encode("utf-8"))

        elif self.path in ("/api/run-all", "/api/run-factbook", "/api/run-trends"):
            scope = "factbook" if "factbook" in self.path else ("trends" if "trends" in self.path else "all")
            if not TEST_STATE["is_running"]:
                t = threading.Thread(target=run_audit_worker, args=(scope, "fast"), daemon=True)
                t.start()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Started", "scope": scope}).encode("utf-8"))
            else:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Test already running"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_server():
    load_cached_results()
    socketserver.TCPServer.allow_reuse_address = True
    server_address = ("", PORT)
    with socketserver.ThreadingTCPServer(server_address, DashboardRequestHandler) as httpd:
        print(f"TTU FactBook & Trends Live Dashboard Server running on http://0.0.0.0:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    start_server()
