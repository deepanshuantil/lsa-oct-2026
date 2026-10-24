"""All folders, file names and expected numbers live here. No paths are hard-coded
anywhere else, so the same code runs on Colab and on a laptop.

Override locations with environment variables (handy on Colab):
    LSA_ROOT    project folder          (default: the folder containing this file)
    LSA_SOURCE  where the original NHS files are kept (default: data/raw)
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("LSA_ROOT", Path(__file__).resolve().parent))
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
LOGS = ROOT / "logs"
SOURCE = Path(os.environ.get("LSA_SOURCE", RAW))

# File names
REGIONAL_CSV = "appointments_regional.csv"
CATEGORIES_CSV = "national_categories.csv"
DURATION_XLSX = "actual_duration.csv.xlsx"   # an Excel file despite its name
DURATION_CSV = "actual_duration.csv"
MANIFEST = "manifest.json"

# Names of the clean Parquet datasets (folders inside CLEAN)
CLEAN_REGIONAL = "regional"
CLEAN_CATEGORIES = "categories"
CLEAN_DURATION = "duration"

# Numbers the brief says you must get on the real files
EXPECTED_ROWS = {REGIONAL_CSV: 596_821, CATEGORIES_CSV: 817_394, DURATION_CSV: 137_793}
EXPECTED_TOTALS = {CLEAN_REGIONAL: 742_804_525, CLEAN_CATEGORIES: 296_046_770, CLEAN_DURATION: 167_980_692}
EXPECTED_REGIONAL_ROWS_AFTER_SUM = 295_692

SHUFFLE_PARTITIONS = 8   # default is 200: far too many for one machine

# ----------------------------------------------------------------- Week 3: warehouse
WAREHOUSE = ROOT / "warehouse" / "warehouse.duckdb"
QUALITY_REPORT = ROOT / "docs" / "quality_report.json"

# dim_geography is built from the duration file: 106 sub-ICB locations
EXPECTED_GEOGRAPHY_ROWS = 106

# dim_date covers every day in this range (regional file starts Jan 2020, all files end Jun 2022)
DATE_RANGE = ("2020-01-01", "2022-12-31")

# The regional and category files only overlap here (first day of each month, inclusive)
RECON_WINDOW = ("2021-08-01", "2022-06-01")

# The duration file will NOT reach 100% of the category file (about 90.9 to 92.2%)
MIN_DURATION_COVERAGE = 0.90

# Known bands with an explicit sort order (alphabetical would put "1 Day" before "Same Day").
# (label, is_known): "Unknown / Data Quality" is excluded from rates that need a known value.
BOOKING_WAIT_BANDS = [
    ("Same Day", True), ("1 Day", True), ("2 to 7 Days", True), ("8 to 14 Days", True),
    ("15 to 21 Days", True), ("22 to 28 Days", True), ("More than 28 Days", True),
    ("Unknown / Data Quality", False),
]
DURATION_BANDS = [
    ("1-5 Minutes", True), ("6-10 Minutes", True), ("11-15 Minutes", True), ("16-20 Minutes", True),
    ("21-30 Minutes", True), ("31-60 Minutes", True), ("Unknown / Data Quality", False),
]

# Exit codes of run_pipeline.py
EXIT_OK = 0
EXIT_CRASH = 1
EXIT_CHECK_FAILED = 2
