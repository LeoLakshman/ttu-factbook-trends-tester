"""
TTU FactBook MC College Automated Test & Verification Suite.
CLI entry point for authenticating, fetching, comparing, and validating
Production vs Development FactBook pages for College of Media & Communication.
"""

import argparse
import getpass
import os
import sys
import json
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import requests
from requests_ntlm import HttpNtlmAuth
import urllib3
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Local modules
from config import PROD_BASE_URL, DEV_BASE_URL, KEY_MC_PAGES, load_all_subpages
from parser import parse_factbook_page
from validator import compare_pages, validate_cross_page_rollups, Severity
from reporter import generate_html_report

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning)

console = Console()


def create_session(user: Optional[str] = None, password: Optional[str] = None, domain: str = "TTU") -> Tuple[requests.Session, requests.Session]:
    """Create HTTP sessions for Prod and Dev."""
    prod_session = requests.Session()
    prod_session.verify = False
    prod_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    dev_session = requests.Session()
    dev_session.verify = False
    dev_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    if user and password:
        # Format domain\username if domain not already present
        full_user = user if "\\" in user or "@" in user else f"{domain}\\{user}"
        dev_session.auth = HttpNtlmAuth(full_user, password)

    return prod_session, dev_session


def verify_dev_access(dev_session: requests.Session) -> bool:
    """Test if dev server responds with 200 OK using current auth."""
    url = f"{DEV_BASE_URL}/FactBook/"
    try:
        r = dev_session.get(url, timeout=12)
        if r.status_code == 200:
            return True
        elif r.status_code == 401:
            console.print(f"[bold red]❌ Dev Authentication Failed (HTTP 401 Unauthorized) at {url}[/bold red]")
            console.print("[yellow]Please check your TTU/eRaider username, password, or VPN connection.[/yellow]")
            return False
        else:
            console.print(f"[bold yellow]⚠️ Dev Server responded with HTTP {r.status_code} at {url}[/bold yellow]")
            return False
    except Exception as e:
        console.print(f"[bold red]❌ Connection error to Dev server ({url}): {e}[/bold red]")
        return False


def run_tests(
    subpages: List[Dict[str, Any]],
    user: Optional[str] = None,
    password: Optional[str] = None,
    domain: str = "TTU",
    mock_mode: bool = False,
    output_dir: Path = Path("./reports")
):
    """Run full test and validation loop across subpages."""
    output_dir.mkdir(parents=True, exist_ok=True)
    prod_session, dev_session = create_session(user, password, domain)

    if not mock_mode:
        console.print(f"[cyan]Testing authentication against Dev ({DEV_BASE_URL})...[/cyan]")
        if not verify_dev_access(dev_session):
            console.print("[bold red]Aborting test run. Dev authentication did not succeed.[/bold red]")
            console.print("[dim]Tip: You can use --mock to preview the reporting pipeline with synthetic changes.[/dim]")
            sys.exit(1)
        console.print("[bold green]✓ Dev NTLM Authentication Successful![/bold green]\n")
    else:
        console.print("[bold yellow]Running in --mock mode (simulating Dev responses for testing)...[/bold yellow]\n")

    results: List[Dict[str, Any]] = []
    page_results_map: Dict[str, Dict[str, Any]] = {}

    console.print(f"Beginning FactBook MC College audit across [bold]{len(subpages)}[/bold] subpages...\n")

    with console.status("[bold green]Crawling and validating subpages...") as status:
        for idx, page in enumerate(subpages):
            rel_path = page["path"].strip()
            # Ensure proper case for FactBook
            clean_path = rel_path if rel_path.startswith("/") else f"/{rel_path}"
            prod_url = f"{PROD_BASE_URL}{clean_path}"
            dev_url = f"{DEV_BASE_URL}{clean_path}"

            status.update(f"Testing [{idx+1}/{len(subpages)}] {page.get('title', clean_path)}...")

            # 1. Fetch Production
            try:
                r_prod = prod_session.get(prod_url, timeout=15)
                prod_data = parse_factbook_page(r_prod.text, prod_url, r_prod.status_code)
            except Exception as e:
                prod_data = parse_factbook_page("", prod_url, 0)
                prod_data["error"] = str(e)

            # 2. Fetch Development (or Mock)
            if not mock_mode:
                try:
                    r_dev = dev_session.get(dev_url, timeout=15)
                    dev_data = parse_factbook_page(r_dev.text, dev_url, r_dev.status_code)
                except Exception as e:
                    dev_data = parse_factbook_page("", dev_url, 0)
                    dev_data["error"] = str(e)
            else:
                # Mock dev by using prod data with sample simulated changes
                dev_data = json.loads(json.dumps(prod_data))
                dev_data["url"] = dev_url
                if "ENRDEPT" in clean_path and dev_data.get("mc_rows"):
                    # Simulate an update in Dev
                    for r in dev_data["mc_rows"]:
                        if "COMS" in r.get("raw_cells", []):
                            r["UNDERGRAD"] = "375"
                            r["UNDERGRAD__num"] = 375.0
                            r["TOTAL"] = "410"
                            r["TOTAL__num"] = 410.0

            # 3. Compare and Validate
            comparison = compare_pages(prod_data, dev_data, page)
            results.append(comparison)
            page_results_map[clean_path] = comparison

    # 4. Cross-page Rollup Validation
    cross_page_flags = validate_cross_page_rollups(page_results_map)

    # 5. Generate Reports
    html_file = output_dir / "mc_factbook_audit_report.html"
    json_file = output_dir / "mc_factbook_audit_data.json"

    generate_html_report(results, cross_page_flags, html_file)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({"results": results, "cross_flags": cross_page_flags}, f, indent=2)

    # 6. Display Rich Console Summary
    display_cli_summary(results, cross_page_flags, html_file)


def display_cli_summary(results: List[Dict[str, Any]], cross_page_flags: List[Dict[str, Any]], html_file: Path):
    """Print executive table and status summary in terminal."""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASSED")
    changed = sum(1 for r in results if r["status"] == "CHANGED")
    flagged = sum(1 for r in results if r["status"] == "FLAGGED")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    table = Table(title="TTU FactBook MC College Audit Results", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="dim", width=18)
    table.add_column("Subpage Title", width=36)
    table.add_column("Status", width=12)
    table.add_column("Changes", width=10, justify="right")
    table.add_column("Flags / Uncertainties", width=35)

    for r in results:
        status_style = {
            "PASSED": "[green]PASSED[/green]",
            "CHANGED": "[cyan]CHANGED[/cyan]",
            "FLAGGED": "[bold yellow]FLAGGED[/bold yellow]",
            "ERROR": "[bold red]ERROR[/bold red]"
        }.get(r["status"], r["status"])

        flags_text = ""
        if r.get("flags"):
            flags_text = "; ".join(f["message"][:32] + "..." for f in r["flags"])
        elif r["status"] == "PASSED":
            flags_text = "[green]✓ Exact match[/green]"

        changes_count = str(len(r.get("changes", []))) if r.get("changes") else "-"

        table.add_row(
            r["category"][:18],
            r["title"][:36],
            status_style,
            changes_count,
            flags_text[:35]
        )

    console.print("\n")
    console.print(table)

    summary_panel = Panel(
        f"[bold]Total Subpages Checked:[/bold] {total}\n"
        f"[green]✓ Passed (Exact Match):[/green] {passed}\n"
        f"[cyan]🔄 Changed (Data Updated):[/cyan] {changed}\n"
        f"[yellow]⚠️ Flagged (Uncertainties / Math):[/yellow] {flagged}\n"
        f"[red]❌ Errors (HTTP / Server):[/red] {errors}\n\n"
        f"[bold underline]Interactive HTML Dashboard Saved to:[/bold underline]\n"
        f"[bold cyan]{html_file.resolve()}[/bold cyan]",
        title="[bold]FactBook Audit Summary[/bold]",
        border_style="red"
    )
    console.print(summary_panel)


def main():
    parser = argparse.ArgumentParser(description="TTU FactBook MC College Test and Validation Suite")
    parser.add_argument("-u", "--user", help="TTU / eRaider Username (can also use env TTU_USER)")
    parser.add_argument("-p", "--password", help="TTU / eRaider Password (can also use env TTU_PASS)")
    parser.add_argument("--domain", default="TTU", help="Windows Domain (default: TTU)")
    parser.add_argument("--quick", action="store_true", help="Run priority MC pages (27 key pages)")
    parser.add_argument("--all", action="store_true", help="Run all 155 FactBook subpages")
    parser.add_argument("--category", help="Filter by category (e.g. Enrollment, Degree, Course, Faculty)")
    parser.add_argument("--pages", help="Comma-separated paths or keywords to test (e.g. ENRCOLL,ENRDEPT)")
    parser.add_argument("--mock", action="store_true", help="Mock Dev responses (for dry-run testing without dev login)")
    parser.add_argument("--output-dir", default="./reports", help="Output directory for reports")

    args = parser.parse_args()

    user = args.user or os.environ.get("TTU_USER")
    password = args.password or os.environ.get("TTU_PASS")

    # If not mock mode and user not specified, prompt securely
    if not args.mock and not user:
        console.print("[bold cyan]TTU eRaider / Windows NTLM Authentication Required for Dev Server[/bold cyan]")
        user = input("Enter TTU / eRaider Username (e.g. erasmith or TTU\\erasmith): ").strip()
        if not user:
            console.print("[yellow]No username provided. Defaulting to --mock dry run mode.[/yellow]")
            args.mock = True

    if not args.mock and not password:
        password = getpass.getpass("Enter TTU / eRaider Password: ")

    # Select subpages
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

    if not subpages:
        console.print("[bold red]No matching subpages found for specified filters.[/bold red]")
        sys.exit(1)

    run_tests(
        subpages=subpages,
        user=user,
        password=password,
        domain=args.domain,
        mock_mode=args.mock,
        output_dir=Path(args.output_dir)
    )


if __name__ == "__main__":
    main()
