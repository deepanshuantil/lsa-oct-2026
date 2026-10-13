"""
Extract stage: copy the three source files into data/raw/, convert the Excel
file to CSV, and write manifest.json.

The raw copies are NEVER edited. If anything goes wrong later, rebuild from raw.

Usage (from the repo root):
    python src/extract.py --source /path/to/folder/with/the/files

Optional: --dest data/raw   (default)
"""
import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REGIONAL = "appointments_regional.csv"
CATEGORIES = "national_categories.csv"
DURATION_XLSX = "actual_duration.csv.xlsx"   # an Excel file, despite the name
DURATION_CSV = "actual_duration.csv"

# Row counts the plan says you must get. A mismatch means something is wrong.
EXPECTED_ROWS = {REGIONAL: 596_821, CATEGORIES: 817_394, DURATION_CSV: 137_793}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_rows(path: Path) -> int:
    """Number of data rows, excluding the header. Uses the csv module so a
    quoted field containing a line break is not counted as two rows.
    utf-8-sig only affects how we READ; the file on disk is untouched."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def describe(path: Path, rows: int, extracted_at: str, **extra) -> dict:
    return {
        "file_name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "row_count": rows,
        "extracted_at": extracted_at,
        **extra,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="folder holding the three source files")
    ap.add_argument("--dest", default="data/raw", help="where raw copies go (default data/raw)")
    args = ap.parse_args()

    source, dest = Path(args.source), Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    # 1. Copy the three files byte-for-byte (copy2 also keeps timestamps)
    for name in (REGIONAL, CATEGORIES, DURATION_XLSX):
        src = source / name
        if not src.exists():
            raise FileNotFoundError(f"Missing source file: {src}")
        shutil.copy2(src, dest / name)
        print(f"copied {name}")

    # 2. Convert the Excel file to CSV. dtype=str keeps every value exactly as
    #    written (no guessed types) and keep_default_na=False keeps blanks blank.
    xlsx_path = dest / DURATION_XLSX
    sheets = pd.ExcelFile(xlsx_path).sheet_names
    print(f"{DURATION_XLSX} has sheet(s): {sheets}; converting the first")
    df = pd.read_excel(xlsx_path, sheet_name=0, dtype=str, keep_default_na=False)
    csv_path = dest / DURATION_CSV
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"converted to {DURATION_CSV} ({len(df):,} rows)")

    # 3. Build the manifest
    extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    files = [
        describe(dest / REGIONAL, count_csv_rows(dest / REGIONAL), extracted_at),
        describe(dest / CATEGORIES, count_csv_rows(dest / CATEGORIES), extracted_at),
        describe(
            csv_path, count_csv_rows(csv_path), extracted_at,
            converted_from=DURATION_XLSX,
            source_sha256=sha256_of(xlsx_path),
        ),
    ]
    manifest = {"extracted_at": extracted_at, "files": files}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # 4. Check against the counts the plan expects
    print("\nRow count check:")
    ok = True
    for entry in files:
        want = EXPECTED_ROWS[entry["file_name"]]
        got = entry["row_count"]
        status = "OK" if got == want else "MISMATCH"
        ok &= got == want
        print(f"  {entry['file_name']:<28} {got:>9,}  expected {want:>9,}  {status}")
    print("\nmanifest.json written to", dest)
    if not ok:
        raise SystemExit("Row counts do not match the expected values. Investigate before continuing.")


if __name__ == "__main__":
    main()# extract stage
