"""KPI stage: ask the warehouse the dashboard's questions and save the answers as small files.

Why a separate step? The warehouse file is large and is not in Git. The dashboard only needs a
few small summary tables, so we export those (counts only, never rates) into app/data/ and the
dashboard reads them. Rates such as the DNA rate are calculated by the dashboard from the counts,
which is the "store counts, calculate rates at query time" rule from the brief.

    python src/kpis.py                      # warehouse/warehouse.duckdb -> app/data/*.csv
"""
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

log = logging.getLogger("kpis")

# Which labels count as what. Written once, here, so every KPI uses the same definition.
LONG_WAIT = ("15 to 21 Days", "22 to 28 Days", "More than 28 Days")   # booked more than 14 days ahead
LONGER_THAN_15_MIN = ("16-20 Minutes", "21-30 Minutes", "31-60 Minutes")
NETWORK_AND_EXTENDED = ("Primary Care Network", "Extended Access Provision")
DATA_QUALITY_CATEGORIES = ("Unmapped", "Inconsistent Mapping")


def _in(values) -> str:
    """Turn a tuple of labels into a SQL list: ('a', 'b')."""
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


# Each query returns one row per month (or per weekday / per ICB-month) of ADDITIVE counts.
QUERIES = {
    # KPI 1 and 2: appointments per month, and the same month one year earlier
    "monthly_totals": """
        WITH m AS (SELECT month_start, SUM(count_of_appointments) AS appointments
                   FROM fact_appointments_monthly GROUP BY 1)
        SELECT m.month_start, m.appointments, p.appointments AS appointments_last_year
        FROM m LEFT JOIN m p ON p.month_start = CAST(m.month_start - INTERVAL 1 YEAR AS DATE)
        ORDER BY 1""",

    # KPI 3 and 4: how far ahead people book. Only appointments with a KNOWN wait are counted.
    "wait_monthly": f"""
        SELECT f.month_start,
               SUM(CASE WHEN f.booking_wait = 'Same Day' THEN f.count_of_appointments END) AS same_day,
               SUM(CASE WHEN f.booking_wait IN {_in(LONG_WAIT)} THEN f.count_of_appointments END) AS long_wait,
               SUM(f.count_of_appointments) AS known_wait
        FROM fact_appointments_monthly f
        JOIN dim_booking_wait w ON w.booking_wait = f.booking_wait
        WHERE w.is_known
        GROUP BY 1 ORDER BY 1""",

    # KPI 5: DNA rate = DNA / (Attended + DNA). Unknown status is kept as its own column.
    "dna_monthly": """
        SELECT month_start,
               SUM(CASE WHEN status = 'Attended' THEN count_of_appointments END) AS attended,
               SUM(CASE WHEN status = 'DNA' THEN count_of_appointments END) AS dna,
               SUM(CASE WHEN status = 'Unknown' THEN count_of_appointments END) AS unknown_status,
               SUM(count_of_appointments) AS total
        FROM fact_appointments_monthly GROUP BY 1 ORDER BY 1""",

    # KPI 6: the same counts per ICB, so the dashboard can rank ICBs over any chosen months
    "dna_by_icb": """
        SELECT icb_code, month_start,
               SUM(CASE WHEN status = 'Attended' THEN count_of_appointments END) AS attended,
               SUM(CASE WHEN status = 'DNA' THEN count_of_appointments END) AS dna
        FROM fact_appointments_monthly GROUP BY 1, 2 ORDER BY 1, 2""",

    # KPI 7 and 8: face-to-face share (of known mode) and GP share (of known staff type)
    "mix_monthly": """
        SELECT month_start,
               SUM(count_of_appointments) AS total,
               SUM(CASE WHEN mode = 'Face-to-Face' THEN count_of_appointments END) AS face_to_face,
               SUM(CASE WHEN mode <> 'Unknown' THEN count_of_appointments END) AS known_mode,
               SUM(CASE WHEN staff_type = 'GP' THEN count_of_appointments END) AS gp,
               SUM(CASE WHEN staff_type <> 'Unknown' THEN count_of_appointments END) AS known_staff
        FROM fact_appointments_monthly GROUP BY 1 ORDER BY 1""",

    # KPI 9: average appointments per day, by day of the week (add up each day, then average)
    "weekday_average": """
        WITH daily AS (SELECT appointment_day, SUM(count_of_appointments) AS appointments
                       FROM fact_appointments_by_category GROUP BY 1)
        SELECT d.weekday_number, d.weekday_name,
               COUNT(*) AS days, SUM(daily.appointments) AS appointments
        FROM daily JOIN dim_date d ON d.date = daily.appointment_day
        GROUP BY 1, 2 ORDER BY 1""",

    # KPI 10 and half of KPI 12: from the categories file, per month
    "category_monthly": f"""
        SELECT month_start,
               SUM(count_of_appointments) AS total,
               SUM(CASE WHEN service_setting IN {_in(NETWORK_AND_EXTENDED)} THEN count_of_appointments END) AS network_extended,
               SUM(CASE WHEN national_category IN {_in(DATA_QUALITY_CATEGORIES)} THEN count_of_appointments END) AS data_quality
        FROM fact_appointments_by_category GROUP BY 1 ORDER BY 1""",

    # KPI 11 and the other half of KPI 12: from the duration file, per month
    "duration_monthly": f"""
        SELECT f.month_start,
               SUM(f.count_of_appointments) AS total,
               SUM(CASE WHEN f.duration_band IN {_in(LONGER_THAN_15_MIN)} THEN f.count_of_appointments END) AS longer_than_15,
               SUM(CASE WHEN d.is_known THEN f.count_of_appointments END) AS known_duration,
               SUM(CASE WHEN NOT d.is_known THEN f.count_of_appointments END) AS unknown_duration
        FROM fact_appointments_by_duration f
        JOIN dim_duration_band d ON d.duration_band = f.duration_band
        GROUP BY 1 ORDER BY 1""",
}


def build(con) -> dict:
    """Run every query. Returns {table name: DataFrame}."""
    out = {}
    for name, sql in QUERIES.items():
        df = con.execute(sql).df()
        for col in df.columns:
            if col == "month_start" or not pd.api.types.is_numeric_dtype(df[col]):
                continue
            if col == "appointments_last_year":
                # No earlier year in the data means "not available", NOT zero: a zero would
                # show a false -100% change. Int64 (capital I) is a whole number that can be blank.
                df[col] = df[col].astype("Int64")
            else:
                df[col] = df[col].fillna(0).astype("int64")      # no matching rows = a real count of 0
        out[name] = df
        log.info("kpis | %s: %s rows", name, f"{len(df):,}")
    return out


def run(warehouse: Path = config.WAREHOUSE, out_dir: Path = config.KPI_DIR,
        report: Path = config.QUALITY_REPORT) -> Path:
    """Export the KPI tables as CSV files, plus a small info file and a copy of the quality report."""
    warehouse, out_dir = Path(warehouse), Path(out_dir)
    if not warehouse.exists():
        raise FileNotFoundError(f"No warehouse at {warehouse}. Run: python run_pipeline.py")
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse), read_only=True)      # read only: exporting never changes the warehouse
    try:
        tables = build(con)
    finally:
        con.close()
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    if Path(report).exists():
        shutil.copy2(report, out_dir / "quality_report.json")
    (out_dir / "info.json").write_text(json.dumps({
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {k: len(v) for k, v in tables.items()}}, indent=2))
    log.info("kpis | wrote %d tables to %s", len(tables), out_dir)
    return out_dir


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run()
