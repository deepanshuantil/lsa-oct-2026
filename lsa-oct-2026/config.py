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
