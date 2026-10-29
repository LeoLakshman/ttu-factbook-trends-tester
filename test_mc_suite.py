"""
Unit and integration tests for TTU FactBook MC validation and testing suite.
"""

import unittest
from parser import parse_factbook_page, parse_numeric
from validator import validate_row_sums, compare_pages, validate_cross_page_rollups, Severity


class TestFactBookMCSuite(unittest.TestCase):

    def test_parse_numeric(self):
        self.assertEqual(parse_numeric("1,753"), 1753.0)
        self.assertEqual(parse_numeric("0"), 0.0)
        self.assertEqual(parse_numeric("45.2%"), 45.2)
        self.assertEqual(parse_numeric("-"), 0.0)
        self.assertIsNone(parse_numeric(""))
        self.assertIsNone(parse_numeric("Hello"))

    def test_validate_row_sums_clean(self):
        headers = ["COLLEGE", "COLLEGE NAME", "UNDERGRAD", "GRAD", "LAW", "VET SCHOOL", "TOTAL"]
        row = {
            "UNDERGRAD__num": 1753.0,
            "GRAD__num": 320.0,
            "LAW__num": 0.0,
            "VET SCHOOL__num": 0.0,
            "TOTAL__num": 2073.0,
        }
        flags = validate_row_sums(headers, row)
        self.assertEqual(len(flags), 0, "Expected no math flags for valid row")

    def test_validate_row_sums_mismatch(self):
        headers = ["COLLEGE", "COLLEGE NAME", "UNDERGRAD", "GRAD", "TOTAL"]
        row = {
            "UNDERGRAD__num": 1000.0,
            "GRAD__num": 500.0,
            "TOTAL__num": 1600.0,  # 1000 + 500 != 1600
        }
        flags = validate_row_sums(headers, row)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["type"], "ROW_SUM_MISMATCH")
        self.assertEqual(flags[0]["severity"], Severity.HIGH)

    def test_compare_pages_drop_to_zero_flag(self):
        prod_data = {
            "url": "https://techdata.irs.ttu.edu/FactBook/Enrollment/ENRDEPT.aspx",
            "status_code": 200,
            "headers": ["COLLEGE", "DEPT", "DEPARTMENT", "UNDERGRAD", "TOTAL"],
            "mc_rows": [
                {
                    "raw_cells": ["MC", "ADBS", "Advertising & Brand Strategy", "290", "290"],
                    "COLLEGE": "MC", "DEPT": "ADBS",
                    "UNDERGRAD__num": 290.0, "TOTAL__num": 290.0
                }
            ],
            "all_rows": [{}]
        }
        # In Dev, ADBS suddenly has 0 undergrads
        dev_data = {
            "url": "https://devapps.irim.ttu.edu/FactBook/Enrollment/ENRDEPT.aspx",
            "status_code": 200,
            "headers": ["COLLEGE", "DEPT", "DEPARTMENT", "UNDERGRAD", "TOTAL"],
            "mc_rows": [
                {
                    "raw_cells": ["MC", "ADBS", "Advertising & Brand Strategy", "0", "0"],
                    "COLLEGE": "MC", "DEPT": "ADBS",
                    "UNDERGRAD__num": 0.0, "TOTAL__num": 0.0
                }
            ],
            "all_rows": [{}]
        }
        meta = {"title": "Enrollment by Department", "category": "Enrollment", "path": "/FactBook/Enrollment/ENRDEPT.aspx"}
        comp = compare_pages(prod_data, dev_data, meta)
        
        self.assertEqual(comp["status"], "FLAGGED")
        zero_flags = [f for f in comp["flags"] if f["type"] == "UNEXPECTED_ZERO"]
        self.assertTrue(len(zero_flags) > 0, "Expected UNEXPECTED_ZERO flag")

    def test_cross_page_rollup_check(self):
        page_results = {
            "/FactBook/Enrollment/ENRCOLL.aspx": {
                "dev_summary": {"mc_total": ["MC", "Coll of Media and Communicatn", "1753", "320", "0", "0", "2073"]}
            },
            "/FactBook/Enrollment/ENRDEPT.aspx": {
                "dev_summary": {"mc_total": ["MC", "", "", "1750", "320", "0", "0", "2070"]}  # 2070 != 2073
            }
        }
        flags = validate_cross_page_rollups(page_results)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["type"], "CROSS_PAGE_ROLLUP_MISMATCH")


if __name__ == "__main__":
    unittest.main()
