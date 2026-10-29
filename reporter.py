"""
Reporter module for TTU FactBook comparison and validation suite.
Generates an interactive, standalone HTML dashboard and rich CLI summaries.
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


def generate_html_report(
    results: List[Dict[str, Any]],
    cross_page_flags: List[Dict[str, Any]],
    output_path: Path
) -> str:
    """Generate a responsive, standalone HTML report with filters and interactive diffs."""
    total_pages = len(results)
    passed_pages = sum(1 for r in results if r["status"] == "PASSED")
    changed_pages = sum(1 for r in results if r["status"] == "CHANGED")
    flagged_pages = sum(1 for r in results if r["status"] == "FLAGGED")
    error_pages = sum(1 for r in results if r["status"] == "ERROR")

    # Collect total changes and flags
    total_flags = sum(len(r.get("flags", [])) for r in results) + len(cross_page_flags)
    total_changes = sum(len(r.get("changes", [])) for r in results)

    results_json = json.dumps(results, indent=2)
    cross_flags_json = json.dumps(cross_page_flags, indent=2)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TTU FactBook MC College Audit Report</title>
    <style>
        :root {{
            --ttu-red: #CC0000;
            --ttu-dark-red: #990000;
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
            background: linear-gradient(135deg, #111111 0%, #2a0000 100%);
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
        .header h1 {{
            font-size: 24px;
            font-weight: 700;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .header .subtitle {{
            color: #d1d5db;
            font-size: 14px;
            margin-top: 6px;
        }}
        .header-meta {{
            text-align: right;
            font-size: 13px;
            color: #9ca3af;
        }}

        /* KPI Dashboard Cards */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
            text-align: left;
        }}
        .kpi-card .kpi-label {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
        }}
        .kpi-card .kpi-value {{
            font-size: 32px;
            font-weight: 700;
            margin-top: 8px;
        }}
        .kpi-card.passed .kpi-value {{ color: var(--pass-color); }}
        .kpi-card.changed .kpi-value {{ color: var(--info-color); }}
        .kpi-card.flagged .kpi-value {{ color: var(--warn-color); }}
        .kpi-card.error .kpi-value {{ color: var(--danger-color); }}

        /* Controls / Filter Bar */
        .control-bar {{
            background: var(--card-bg);
            padding: 16px 20px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            align-items: center;
            justify-content: space-between;
        }}
        .filter-buttons {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
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
        .btn:hover {{
            background: #f1f5f9;
        }}
        .btn.active {{
            background: var(--ttu-red);
            color: white;
            border-color: var(--ttu-red);
        }}
        .badge {{
            padding: 2px 7px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 700;
        }}
        .btn.active .badge {{
            background: rgba(255,255,255,0.3);
            color: white;
        }}
        .search-box input {{
            padding: 8px 14px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 13px;
            width: 260px;
        }}

        /* Cross page alerts */
        .alert-box {{
            background: #fffbeb;
            border-left: 4px solid var(--warn-color);
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .alert-box h4 {{
            color: #b45309;
            margin-bottom: 6px;
            font-size: 14px;
            font-weight: 700;
        }}

        /* Page Report Cards */
        .pages-container {{
            display: flex;
            flex-direction: column;
            gap: 18px;
        }}
        .page-card {{
            background: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border-color);
            box-shadow: 0 2px 4px rgba(0,0,0,0.03);
            overflow: hidden;
        }}
        .page-card-header {{
            padding: 16px 20px;
            background: #fafbfc;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
        }}
        .page-card-header:hover {{
            background: #f1f5f9;
        }}
        .page-title-group {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .category-tag {{
            background: #e2e8f0;
            color: #475569;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .page-title {{
            font-size: 16px;
            font-weight: 600;
        }}
        .status-pill {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .status-pill.PASSED {{ background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }}
        .status-pill.CHANGED {{ background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }}
        .status-pill.FLAGGED {{ background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }}
        .status-pill.ERROR {{ background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }}

        .page-card-body {{
            padding: 20px;
        }}

        /* Flags Container */
        .flag-item {{
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 10px;
            font-size: 13px;
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .flag-item.HIGH, .flag-item.CRITICAL {{
            background: #fef2f2;
            color: #991b1b;
            border-left: 4px solid var(--danger-color);
        }}
        .flag-item.MEDIUM {{
            background: #fffbeb;
            color: #92400e;
            border-left: 4px solid var(--warn-color);
        }}
        .flag-item.LOW, .flag-item.INFO {{
            background: #eff6ff;
            color: #1e40af;
            border-left: 4px solid var(--info-color);
        }}

        /* Change Table */
        .diff-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 13px;
        }}
        .diff-table th, .diff-table td {{
            padding: 10px 12px;
            text-align: left;
            border: 1px solid var(--border-color);
        }}
        .diff-table th {{
            background: #f8fafc;
            color: var(--text-muted);
            font-weight: 600;
        }}
        .delta-pos {{ color: #059669; font-weight: 600; }}
        .delta-neg {{ color: #dc2626; font-weight: 600; }}
        .delta-zero {{ color: var(--text-muted); }}

        .links-bar {{
            margin-top: 14px;
            display: flex;
            gap: 12px;
            font-size: 12px;
        }}
        .links-bar a {{
            color: var(--ttu-red);
            text-decoration: none;
            font-weight: 600;
        }}
        .links-bar a:hover {{
            text-decoration: underline;
        }}

        .functionality-tags {{
            display: flex;
            gap: 10px;
            margin-top: 12px;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .func-tag {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .func-tag.ok {{ color: #059669; }}
        .func-tag.fail {{ color: #dc2626; }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>Texas Tech University - FactBook MC College Audit</h1>
            <div class="subtitle">Verification, Change Detection & Mathematical Integrity Test Suite for College of Media & Communication</div>
        </div>
        <div class="header-meta">
            <div><strong>Generated:</strong> {timestamp}</div>
            <div><strong>Production:</strong> techdata.irs.ttu.edu</div>
            <div><strong>Development:</strong> devapps.irim.ttu.edu</div>
        </div>
    </div>

    <!-- KPI Row -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Subpages Tested</div>
            <div class="kpi-value">{total_pages}</div>
        </div>
        <div class="kpi-card passed">
            <div class="kpi-label">Passed / Exact Match</div>
            <div class="kpi-value">{passed_pages}</div>
        </div>
        <div class="kpi-card changed">
            <div class="kpi-label">Changes Detected</div>
            <div class="kpi-value">{changed_pages}</div>
        </div>
        <div class="kpi-card flagged">
            <div class="kpi-label">Flagged Discrepancies</div>
            <div class="kpi-value">{flagged_pages}</div>
        </div>
        <div class="kpi-card error">
            <div class="kpi-label">Server / HTTP Errors</div>
            <div class="kpi-value">{error_pages}</div>
        </div>
    </div>

    <!-- Cross page rollup alert if any -->
    <div id="crossPageAlerts"></div>

    <!-- Control Bar -->
    <div class="control-bar">
        <div class="filter-buttons">
            <button class="btn active" onclick="filterStatus('ALL')">All Pages <span class="badge">{total_pages}</span></button>
            <button class="btn" onclick="filterStatus('FLAGGED')">⚠️ Flagged <span class="badge" style="background:#fef3c7; color:#92400e;">{flagged_pages}</span></button>
            <button class="btn" onclick="filterStatus('CHANGED')">🔄 Changed <span class="badge" style="background:#e0f2fe; color:#0369a1;">{changed_pages}</span></button>
            <button class="btn" onclick="filterStatus('PASSED')">✅ Matches <span class="badge" style="background:#d1fae5; color:#065f46;">{passed_pages}</span></button>
            <button class="btn" onclick="filterStatus('ERROR')">❌ Errors <span class="badge" style="background:#fee2e2; color:#991b1b;">{error_pages}</span></button>
        </div>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search page, category, dept..." onkeyup="filterCards()">
        </div>
    </div>

    <!-- Pages List -->
    <div class="pages-container" id="pagesContainer"></div>

    <script>
        const results = {results_json};
        const crossFlags = {cross_flags_json};

        // Render Cross Page Flags
        if (crossFlags && crossFlags.length > 0) {{
            const alertDiv = document.getElementById('crossPageAlerts');
            alertDiv.innerHTML = `
                <div class="alert-box">
                    <h4>⚠️ Cross-Page Rollup Inconsistencies Detected</h4>
                    <ul>
                        ${{crossFlags.map(cf => `<li><strong>${{cf.type}}:</strong> ${{cf.message}}</li>`).join('')}}
                    </ul>
                </div>
            `;
        }}

        // Render Page Cards
        function renderCards(filter = 'ALL', search = '') {{
            const container = document.getElementById('pagesContainer');
            container.innerHTML = '';
            const searchLower = search.toLowerCase();

            results.forEach((item, index) => {{
                if (filter !== 'ALL' && item.status !== filter) return;
                
                const searchableText = `${{item.title}} ${{item.category}} ${{item.path}} ${{JSON.stringify(item.changes || [])}}`.toLowerCase();
                if (searchLower && !searchableText.includes(searchLower)) return;

                const card = document.createElement('div');
                card.className = `page-card page-status-${{item.status}}`;

                let flagsHtml = '';
                if (item.flags && item.flags.length > 0) {{
                    flagsHtml = item.flags.map(f => `
                        <div class="flag-item ${{f.severity}}">
                            <strong>[${{f.severity}}] ${{f.type}}:</strong> ${{f.message}}
                        </div>
                    `).join('');
                }}

                let changesHtml = '';
                if (item.changes && item.changes.length > 0) {{
                    changesHtml = `
                        <h4 style="margin-top:12px; font-size:13px; font-weight:600;">Data Changes Detected for MC:</h4>
                        <table class="diff-table">
                            <thead>
                                <tr>
                                    <th>Entity / Dept</th>
                                    <th>Metric</th>
                                    <th>Production</th>
                                    <th>Development</th>
                                    <th>Delta (Δ)</th>
                                    <th>% Change</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${{item.changes.map(c => {{
                                    if (c.type === 'NUMERIC_CHANGE') {{
                                        const deltaClass = c.delta > 0 ? 'delta-pos' : (c.delta < 0 ? 'delta-neg' : 'delta-zero');
                                        const sign = c.delta > 0 ? '+' : '';
                                        return `
                                            <tr>
                                                <td><strong>${{c.entity || ''}}</strong></td>
                                                <td>${{c.metric || ''}}</td>
                                                <td>${{c.prod !== null ? c.prod.toLocaleString() : '-'}}</td>
                                                <td><strong>${{c.dev !== null ? c.dev.toLocaleString() : '-'}}</strong></td>
                                                <td class="${{deltaClass}}">${{sign}}${{c.delta.toLocaleString()}}</td>
                                                <td>${{sign}}${{c.pct_change}}%</td>
                                            </tr>
                                        `;
                                    }} else {{
                                        return `
                                            <tr>
                                                <td><strong>${{c.field || c.entity || 'Change'}}</strong></td>
                                                <td colspan="5">${{c.note || JSON.stringify(c)}}</td>
                                            </tr>
                                        `;
                                    }}
                                }}).join('')}}
                            </tbody>
                        </table>
                    `;
                }} else if (item.status === 'PASSED') {{
                    changesHtml = `<p style="font-size:13px; color:var(--text-muted); margin-top:8px;">✅ All MC metrics and table headers match production exactly.</p>`;
                }}

                const func = item.functionality || {{}};
                const funcHtml = `
                    <div class="functionality-tags">
                        <span class="func-tag ${{func.dev_http === 200 ? 'ok' : 'fail'}}">HTTP ${{func.dev_http || '-'}}</span>
                        <span class="func-tag ${{func.dev_table_present ? 'ok' : 'fail'}}">Grid: ${{func.dev_table_present ? 'Rendered' : 'Missing'}}</span>
                        <span class="func-tag ${{func.dev_excel_export ? 'ok' : 'fail'}}">Excel: ${{func.dev_excel_export ? 'Yes' : 'No'}}</span>
                        <span class="func-tag ${{func.dev_pdf_export ? 'ok' : 'fail'}}">PDF: ${{func.dev_pdf_export ? 'Yes' : 'No'}}</span>
                        <span class="func-tag">Terms Available: ${{func.dropdown_options_count || 0}}</span>
                    </div>
                `;

                card.innerHTML = `
                    <div class="page-card-header" onclick="toggleCardBody(${{index}})">
                        <div class="page-title-group">
                            <span class="category-tag">${{item.category}}</span>
                            <span class="page-title">${{item.title}}</span>
                        </div>
                        <span class="status-pill ${{item.status}}">${{item.status}}</span>
                    </div>
                    <div class="page-card-body" id="card-body-${{index}}">
                        ${{flagsHtml}}
                        ${{changesHtml}}
                        ${{funcHtml}}
                        <div class="links-bar">
                            <a href="${{item.prod_url}}" target="_blank">🔗 View Production Page</a>
                            <a href="${{item.dev_url}}" target="_blank">🔗 View Dev Page</a>
                            <span style="color:var(--text-muted); margin-left:auto;">Path: ${{item.path}}</span>
                        </div>
                    </div>
                `;
                container.appendChild(card);
            }});

            if (container.children.length === 0) {{
                container.innerHTML = `<div style="text-align:center; padding:48px; color:var(--text-muted);">No pages found matching current filter or search criteria.</div>`;
            }}
        }}

        function toggleCardBody(idx) {{
            const body = document.getElementById(`card-body-${{idx}}`);
            if (body) {{
                body.style.display = (body.style.display === 'none') ? 'block' : 'none';
            }}
        }}

        let currentFilter = 'ALL';
        function filterStatus(status) {{
            currentFilter = status;
            document.querySelectorAll('.filter-buttons .btn').forEach(b => b.classList.remove('active'));
            event.target.closest('.btn').classList.add('active');
            renderCards(currentFilter, document.getElementById('searchInput').value);
        }}

        function filterCards() {{
            renderCards(currentFilter, document.getElementById('searchInput').value);
        }}

        // Initial render
        renderCards();
    </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(output_path)
