# Texas Tech University - FactBook & Trends Live Quality Center
### Exhaustive Multi-Attribute Testing, Fault Detection, and Comparative Quality Engine

A production-grade automated testing suite and live interactive dashboard for **TTU FactBook** (`https://techdata.irs.ttu.edu/Factbook/` and `https://devapps.irim.ttu.edu/FactBook/`) and **TTU Trends** (`https://techdata.irs.ttu.edu/Trends/`).

---

## 🌐 Public Live Dashboard

* **Live Public URL**: **[https://48267260022ee8.lhr.life](https://48267260022ee8.lhr.life)**
* **Local Server URL**: `http://localhost:5050`

Whenever you refresh or click **"🚀 Start Audit"**, tests execute live against the TTU servers, streaming live progress and updating error flags.

---

## 🚀 Key Features

### 1. Privilege of Selection (Scope Control)
Run tests tailored to your specific focus area:
* 🌐 **Both FactBook & Trends**: Complete institutional audit across 34 reports.
* 📘 **FactBook Only**: Audits all 13 core FactBook reports across all historical semesters.
* 📈 **Trends Only**: Audits all 21 interactive Trends reports across all Term $\times$ College permutations.

### 2. Pre-Execution Dynamic Time Estimator
Before starting, the dashboard automatically calculates and displays:
* ⏱️ **Estimated Duration**:
  * **Both + Exhaustive**: ~7 to 9 minutes (2,006 permutations)
  * **FactBook + Exhaustive**: ~4 to 5 minutes (1,566 permutations)
  * **Trends + Exhaustive**: ~3 to 4 minutes (440 combinations)
  * **Both + Fast Smoke Check**: ~30 to 35 seconds (34 reports)
  * **FactBook + Fast Smoke Check**: ~15 to 20 seconds
  * **Trends + Fast Smoke Check**: ~10 to 15 seconds
* ⚡ **Exact Permutations Count**: Number of HTTP postbacks and binary file downloads scheduled.
* 📋 **Feature Coverage Breakdown**: Attributes to be verified.

### 3. Three Dedicated Testing Sections
* **Section 1: TTU FactBook Multi-Semester Exhaustive Testing**
  * Tests **every single semester** in the dropdown from **Fall 2026 back to Spring 2009** (up to 62 terms per page).
  * Verifies **Export to Excel** (`.xlsx` binary MIME attachment).
  * Verifies **Export to PDF** (`.pdf` binary file payload).
  * Tests **Exclude foreign campus** (`ForeignIndicator`) checkbox.
  * Tests **Bachelor's degree-seeking transfer** (`transferIndicator`) checkbox.
  * Validates row-level horizontal math ($Col_1 + Col_2 + \dots = \text{Total}$) and subtotals.
  * Expandable **"▼ View All Semesters"** drilldown table.
* **Section 2: TTU Trends Combinatorial Testing**
  * Exhaustively tests all **Term (Fall/Spring) $\times$ College dropdown** combinations.
  * Checks **Exclude foreign campus** checkbox.
  * Verifies **"Export Chart With Data Table"** (`buttonExport`) JavaScript handler (`getSVGText()`).
  * Expandable **"▼ View All Combos"** drilldown table.
* **Section 3: Cross-System Quality Matrix & Discrepancy Tracker**
  * Side-by-side comparison highlighting root causes of real production faults.

---

## 🚨 Production Faults Flagged on Live TTU Servers

1. **Summer Full/Part-Time Zeroed Out ([ENRFULLCOLL.aspx](https://techdata.irs.ttu.edu/FactBook/Enrollment/ENRFULLCOLL.aspx))**:
   * Across all Summer terms (e.g. Summer 2026 `20267`, Summer 2025 `20257`), `FULL` and `PART` columns are zeroed out (`0`), yet reported `TOTAL` is positive (e.g. AG reported Total = 1,701, but $0 + 0 = 0 \neq 1,701$) &rarr; **372 math integrity faults**.
2. **Degrees Report Missing "VET SCHOOL" Column Header ([DEGCOLLDEPTPROG.aspx](https://techdata.irs.ttu.edu/FactBook/Degree/DEGCOLLDEPTPROG.aspx))**:
   * The GridView table header completely omits the column header for `VET SCHOOL`. The 80 DVM degrees are rendered without a column header, failing horizontal sum verifications &rarr; **12 math faults**.
3. **Trends Broken "Export Chart With Data Table" Script (All 21 Pages)**:
   * In `getSVGText()`, line 178 comments out the element reference: `// const tranE1 = document.getElementById("Transition_message_Label");`, but line 187 calls `const msg1 = tranE1.innerText.trim();`.
   * Throws unhandled `ReferenceError: tranE1 is not defined` and alerts `Export failed: tranE1 is not defined` on every page.
4. **Trends Revenue Floating-Point Rounding ([REVSRC.aspx](https://techdata.irs.ttu.edu/Trends/Revenue/REVSRC.aspx))**:
   * Individual revenue fund items differ by \$1-\$2 from the reported `Total` column due to floating-point truncation &rarr; **38 discrepancies**.

---

## ☁️ Deployment on Render.com

This repository includes full configuration for 1-click deployment on [Render.com](https://render.com):

1. **Push this repository to GitHub**:
   ```bash
   git add .
   git commit -m "Deploy TTU FactBook & Trends Live Quality Center"
   git push origin main
   ```
2. **Deploy on Render**:
   * Log into [Render Dashboard](https://dashboard.render.com).
   * Click **New +** &rarr; **Blueprint** (or **Web Service**).
   * Connect your GitHub repository: `LeoLakshman/ttu-factbook-trends-tester`.
   * Render automatically detects `render.yaml`:
     * **Environment**: `Python 3`
     * **Build Command**: `pip install -r requirements.txt`
     * **Start Command**: `python web_server.py`
     * **Port**: Automatically binds to Render's dynamic `$PORT`.
   * Click **Apply / Create Web Service**.
3. Your service will be assigned a permanent public URL (e.g. `https://ttu-factbook-trends-tester.onrender.com`).

---

## 💻 Local CLI Usage

```bash
# Set up virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run Exhaustive All-Attributes Audit (FactBook + Trends)
python exhaustive_tester.py

# Run Live Web Dashboard locally with Public Tunnel
./start_public_dashboard.sh
```
