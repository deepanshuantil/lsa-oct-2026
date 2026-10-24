"""Load stage: clean Parquet -> one DuckDB file holding a star schema.

Facts hold counts, dimensions hold descriptions. The facts are loaded one month at a
time with delete-then-insert inside a transaction, so running the stage again changes
nothing. Nothing is aggregated or de-duplicated here: the look-alike regional rows were
summed in the transform, and doing it again would delete real appointments.

    python src/load.py
"""
import logging
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

log = logging.getLogger("load")

# ---------------------------------------------------------------------------------------
# THE WAREHOUSE DESIGN (a "star schema")
#   Fact tables  = the numbers (count_of_appointments) plus keys pointing at dimensions.
#   Dimension tables = the descriptions (dates, places, labels), one row per thing.
# We have THREE fact tables because the three NHS files describe different things
# (see docs/decision_log.md, decision 14). They are never joined row by row.
# ---------------------------------------------------------------------------------------

# CREATE TABLE IF NOT EXISTS: the table is made the first time and left alone after that,
# so running the load again never wipes the data we already loaded.
FACT_DDL = {
    "fact_appointments_monthly": """
        CREATE TABLE IF NOT EXISTS fact_appointments_monthly (
            month_start DATE, icb_code VARCHAR, status VARCHAR, staff_type VARCHAR,
            mode VARCHAR, booking_wait VARCHAR, count_of_appointments BIGINT)""",
    "fact_appointments_by_category": """
        CREATE TABLE IF NOT EXISTS fact_appointments_by_category (
            month_start DATE, appointment_day DATE, sub_icb_code VARCHAR, service_setting VARCHAR,
            national_category VARCHAR, count_of_appointments BIGINT)""",
    "fact_appointments_by_duration": """
        CREATE TABLE IF NOT EXISTS fact_appointments_by_duration (
            month_start DATE, appointment_day DATE, sub_icb_code VARCHAR, duration_band VARCHAR,
            count_of_appointments BIGINT)""",
}

# How each fact is read from the clean Parquet folders. Each entry is
# (folder name, SQL). The "?" is filled in with ONE month at a time (see replace_month).
# Note there is no DISTINCT and no GROUP BY: the transform already summed the look-alike
# rows, and doing it again here would delete real appointments.
# hive_partitioning = true lets DuckDB read the month_start=... folder names as a column.
FACT_SELECT = {
    "fact_appointments_monthly": ("regional", """
        SELECT CAST(month_start AS DATE), icb_ons_code, appointment_status, hcp_type, appointment_mode,
               time_between_book_and_appointment, count_of_appointments
        FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE CAST(month_start AS DATE) = ?"""),
    "fact_appointments_by_category": ("categories", """
        SELECT CAST(month_start AS DATE), appointment_day, sub_icb_code, service_setting,
               national_category, count_of_appointments
        FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE CAST(month_start AS DATE) = ?"""),
    "fact_appointments_by_duration": ("duration", """
        SELECT CAST(month_start AS DATE), appointment_day, sub_icb_location_code, actual_duration,
               count_of_appointments
        FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE CAST(month_start AS DATE) = ?"""),
}


def _glob(clean_dir: Path, name: str) -> str:
    # Build the file pattern for one dataset, e.g. data/clean/regional/**/*.parquet.
    # The replace() doubles any single quote so the path is safe inside SQL text.
    return str(Path(clean_dir) / name / "**" / "*.parquet").replace("'", "''")


def _assert_unique(con, table: str, column: str) -> None:
    # A dimension key must be unique, otherwise joining a fact to it would repeat rows
    # and inflate the totals. Stop the load straight away if any value appears twice.
    dup = con.execute(f"SELECT COUNT(*) FROM (SELECT {column} FROM {table} GROUP BY {column} HAVING COUNT(*) > 1)").fetchone()[0]
    if dup:
        raise ValueError(f"{table}.{column} must be unique but {dup} value(s) repeat")


# ------------------------------------------------------------------ dimensions
def build_dimensions(con, clean_dir: Path, expected_geography_rows: int | None) -> None:
    """Rebuilt from scratch on every run (CREATE OR REPLACE), so it is idempotent."""
    # dim_date: one row for EVERY calendar day in the range, even days with no data,
    # so charts have no gaps. generate_series makes the list of days.
    start, end = config.DATE_RANGE
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_date AS
        SELECT CAST(d AS DATE) AS date,
               CAST(date_trunc('month', d) AS DATE) AS month_start,
               CAST(year(d) AS INTEGER) AS year,
               CAST(month(d) AS INTEGER) AS month_number,
               strftime(d, '%B') AS month_name,
               CAST(isodow(d) AS INTEGER) AS weekday_number,
               strftime(d, '%A') AS weekday_name,
               isodow(d) >= 6 AS is_weekend
        FROM generate_series(DATE '{start}', DATE '{end}', INTERVAL 1 DAY) AS t(d)""")

    # The two band dimensions: each label gets a sort_order (so "Same Day" comes before
    # "1 Day") and an is_known flag (so "Unknown / Data Quality" can be left out of rates).
    for table, column, bands in (("dim_booking_wait", "booking_wait", config.BOOKING_WAIT_BANDS),
                                 ("dim_duration_band", "duration_band", config.DURATION_BANDS)):
        con.execute(f"CREATE OR REPLACE TABLE {table} ({column} VARCHAR, sort_order INTEGER, is_known BOOLEAN)")
        con.executemany(f"INSERT INTO {table} VALUES (?, ?, ?)",
                        [(label, i, known) for i, (label, known) in enumerate(bands, start=1)])

    # dim_geography: one row per sub-ICB location (106 in the real data).
    # 106 sub-ICB locations with their ICB and region. The duration file is the only one that
    # carries the region code and it lists every location.
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_geography AS
        SELECT DISTINCT sub_icb_location_code AS sub_icb_code, sub_icb_location_ons_code AS sub_icb_ons_code,
               sub_icb_location_name AS sub_icb_name, icb_ons_code AS icb_code, region_ons_code AS region_code
        FROM read_parquet('{_glob(clean_dir, config.CLEAN_DURATION)}', hive_partitioning = true)
        ORDER BY sub_icb_code""")
    _assert_unique(con, "dim_geography", "sub_icb_code")
    # Safety net: if the number of places is not what the profile found, something upstream changed.
    rows = con.execute("SELECT COUNT(*) FROM dim_geography").fetchone()[0]
    if expected_geography_rows is not None and rows != expected_geography_rows:
        raise AssertionError(f"dim_geography has {rows} rows, expected {expected_geography_rows}")

    # The category is what the facts store; its context type is a description of it.
    con.execute(f"""
        CREATE OR REPLACE TABLE dim_national_category AS
        SELECT DISTINCT national_category, context_type
        FROM read_parquet('{_glob(clean_dir, config.CLEAN_CATEGORIES)}', hive_partitioning = true)
        ORDER BY national_category""")
    _assert_unique(con, "dim_national_category", "national_category")

    # Facts that only know the ICB (the regional file) use this view, never dim_geography
    # directly: dim_geography has many rows per ICB, so joining to it would multiply rows.
    con.execute("CREATE OR REPLACE VIEW v_icb AS SELECT DISTINCT icb_code, region_code FROM dim_geography")


# ------------------------------------------------------------------ facts
def replace_month(con, table: str, select_sql: str, month) -> None:
    """Delete this month, then insert it, in ONE transaction. If the insert fails the
    month is put back exactly as it was."""
    # This is what makes the load IDEMPOTENT: run it once or ten times and the month ends
    # up identical, because the old copy is removed before the new one goes in.
    # BEGIN ... COMMIT means both steps happen together or not at all.
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"DELETE FROM {table} WHERE month_start = ?", [month])
        con.execute(f"INSERT INTO {table} {select_sql}", [month])
        con.execute("COMMIT")
    except Exception:
        # Something failed: undo the delete as well, so no month is ever left half loaded.
        con.execute("ROLLBACK")
        raise


def load_fact(con, clean_dir: Path, table: str) -> int:
    # Find which months exist in the clean data, then load them one at a time.
    folder, select = FACT_SELECT[table]
    select_sql = select.format(glob=_glob(clean_dir, folder))
    months = [r[0] for r in con.execute(
        f"SELECT DISTINCT CAST(month_start AS DATE) FROM read_parquet('{_glob(clean_dir, folder)}', "
        f"hive_partitioning = true) ORDER BY 1").fetchall()]
    if not months:
        raise ValueError(f"no Parquet data found for {table} under {clean_dir}/{folder}")
    for month in months:
        replace_month(con, table, select_sql, month)
    return len(months)


def run(clean_dir: Path = config.CLEAN, warehouse: Path = config.WAREHOUSE,
        expected_geography_rows: int | None = config.EXPECTED_GEOGRAPHY_ROWS) -> Path:
    """Load every dimension and fact into `warehouse`. Returns the warehouse path."""
    clean_dir, warehouse = Path(clean_dir), Path(warehouse)
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    # 1 make sure the folder exists, 2 open the database file, 3 build dimensions,
    # 4 load each fact, 5 always close the connection (an open one locks the file).
    t0 = time.time()
    log.info("load start | clean=%s warehouse=%s", clean_dir, warehouse)
    con = duckdb.connect(str(warehouse))
    try:
        build_dimensions(con, clean_dir, expected_geography_rows)
        for table, ddl in FACT_DDL.items():
            con.execute(ddl)
            months = load_fact(con, clean_dir, table)
            rows, total = con.execute(f"SELECT COUNT(*), SUM(count_of_appointments) FROM {table}").fetchone()
            log.info("load | %s: %s months loaded, rows=%s total=%s", table, months, f"{rows:,}", f"{total:,}")
        for table in ("dim_date", "dim_booking_wait", "dim_duration_band", "dim_geography", "dim_national_category"):
            log.info("load | %s: rows=%s", table, f"{con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:,}")
        con.execute("CHECKPOINT")            # flush everything to the .duckdb file on disk
    finally:
        con.close()                      # a held connection would lock the file for the next run
    log.info("load done in %.1fs | 3 facts, 5 dimensions", time.time() - t0)
    return warehouse


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run()
