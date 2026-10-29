"""
Configuration and metadata for TTU FactBook testing and MC College verification.
"""

import json
from pathlib import Path

PROD_BASE_URL = "https://techdata.irs.ttu.edu"
DEV_BASE_URL = "https://devapps.irim.ttu.edu"

# MC College identification metadata
MC_COLLEGE_CODES = {"MC"}
MC_COLLEGE_NAMES = {
    "Coll of Media and Communicatn",
    "Coll of Media and Communication",
    "College of Media & Communication",
    "College of Media and Communication",
    "Media & Communication",
    "Media and Communication",
}

# Known Departments under MC
MC_DEPARTMENT_CODES = {
    "ADBS": "Advertising & Brand Strategy",
    "COMS": "Communication Studies",
    "JCMI": "Journalism & Creative Media",
    "MCOM": "Media and Communication",
    "PCOM": "Professional Communication",
    "PRSC": "Public Rel & Strat Comm Mgmt",
}

# Known Program prefixes under MC
MC_PROGRAM_PREFIXES = ("MC-", "GR-MA-MCOM", "GR-MA-STCM", "GR-ND-MCCR", "GR-PHD-MC", "GR-MA-COMS")

# Priority pages that specifically feature MC college, departments, and programs
KEY_MC_PAGES = [
    {
        "category": "Enrollment",
        "title": "Enrollment - By College",
        "path": "/FactBook/Enrollment/ENRCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By Department",
        "path": "/FactBook/Enrollment/ENRDEPT.aspx",
        "type": "department"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By Program",
        "path": "/FactBook/Enrollment/ENRCOLLDEPTPROG.aspx",
        "type": "program"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By College & Classification",
        "path": "/FactBook/Enrollment/ENRCOLLCLASS.aspx",
        "type": "college"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By College & Full/Part Time",
        "path": "/FactBook/Enrollment/ENRFULLCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By College & Ethnicity",
        "path": "/FactBook/Enrollment/ENRCOLLETH.aspx",
        "type": "college"
    },
    {
        "category": "Enrollment",
        "title": "Enrollment - By College & Gender",
        "path": "/FactBook/Enrollment/ENRCOLLSEX.aspx",
        "type": "college"
    },
    {
        "category": "Degrees/Certificates",
        "title": "Degrees - By College",
        "path": "/FactBook/Degree/DEGCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Degrees/Certificates",
        "title": "Degrees - By Department",
        "path": "/FactBook/Degree/DEGDEPT.aspx",
        "type": "department"
    },
    {
        "category": "Degrees/Certificates",
        "title": "Degrees - By Program",
        "path": "/FactBook/Degree/DEGCOLLDEPTPROG.aspx",
        "type": "program"
    },
    {
        "category": "Degrees/Certificates",
        "title": "Certificates - By College",
        "path": "/FactBook/Degree/CERTCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Course Enrollment",
        "title": "Course Enrollment - By College (Term)",
        "path": "/FactBook/CourseEnrollment/CENCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Course Enrollment",
        "title": "Course Enrollment - By Department (Term)",
        "path": "/FactBook/CourseEnrollment/CENDEPT.aspx",
        "type": "department"
    },
    {
        "category": "Course Enrollment",
        "title": "Course Enrollment - By College (Fiscal Year)",
        "path": "/FactBook/CourseEnrollment/CENCOLLFY.aspx",
        "type": "college"
    },
    {
        "category": "Course Enrollment",
        "title": "Course Enrollment - By Department (Fiscal Year)",
        "path": "/FactBook/CourseEnrollment/CENDEPTFY.aspx",
        "type": "department"
    },
    {
        "category": "Semester Credit Hours",
        "title": "SCH - By College (Term)",
        "path": "/FactBook/SCH/SCHCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Semester Credit Hours",
        "title": "SCH - By Department (Term)",
        "path": "/FactBook/SCH/SCHDEPT.aspx",
        "type": "department"
    },
    {
        "category": "Faculty",
        "title": "Faculty - By College & Gender",
        "path": "/FactBook/Faculty/FACTCOLLGEN.aspx",
        "type": "college"
    },
    {
        "category": "Faculty",
        "title": "Faculty - By College & Tenure",
        "path": "/FactBook/Faculty/FACTCOLLTEN.aspx",
        "type": "college"
    },
    {
        "category": "Faculty",
        "title": "Faculty - By Department & Tenure",
        "path": "/FactBook/Faculty/FACTDEPTTEN.aspx",
        "type": "department"
    },
    {
        "category": "Graduation Rates",
        "title": "Graduation - 4-Year By College",
        "path": "/FactBook/Graduation/GRADCOLL.aspx",
        "type": "college"
    },
    {
        "category": "Graduation Rates",
        "title": "Graduation - 6-Year By College",
        "path": "/FactBook/Graduation/GRAD6COLL.aspx",
        "type": "college"
    },
    {
        "category": "Retention Rates",
        "title": "Retention - One-Year By College",
        "path": "/FactBook/Retention/RETCOLL.aspx",
        "type": "college"
    },
    {
        "category": "New First-Year",
        "title": "New Freshmen - By College",
        "path": "/FactBook/NewFreshman/NEWCOLL.aspx",
        "type": "college"
    },
    {
        "category": "New First-Year",
        "title": "New Freshmen - By Department",
        "path": "/FactBook/NewFreshman/NEWDEPT.aspx",
        "type": "department"
    },
    {
        "category": "Applied/Admitted",
        "title": "Applied/Admitted Freshmen - By College",
        "path": "/FactBook/AppliedAdmitted/APPADMCOLL.aspx?level=nfr",
        "type": "college"
    },
    {
        "category": "Applied/Admitted",
        "title": "Applied/Admitted Freshmen - By Department",
        "path": "/FactBook/AppliedAdmitted/APPADMDEPT.aspx?level=nfr",
        "type": "department"
    },
]


def load_all_subpages():
    """Load all subpages from subpages.json if available, or return KEY_MC_PAGES."""
    json_path = Path(__file__).parent / "subpages.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return KEY_MC_PAGES
