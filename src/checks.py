"""Quality checks that run against the loaded warehouse.

Each check returns a dict {id, name, passed, expected, actual, detail}. A failed check
stops the pipeline (exit code 2). Expected numbers are literal constants from config.py,
never recomputed from the data being checked.

    python src/checks.py
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

log = logging.getLogger("checks")

FACTS = {
    "regional": "fact_appointments_monthly",
    "categories": "fact_appointments_by_category",
    "duration": "fact_appointments_by_duration",
}


def _one(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def _result(cid, name, expected, actual, detail="", ok=None):
    passed = (expected == actual) if ok is None else ok
    return {"id": cid, "name": name, "passed": bool(passed), "expected": expected,
            "actual": actual, "detail": detail}


def check_totals(con, expected_totals):
    """Checks 1-3: each fact table adds up to the number measured in the profile."""
    out = []
    for i, (key, table) in enumerate(FACTS.items(), start=1):
        actual = _one(con, f"SELECT COALESCE(SUM(count_of_appointments), 0) FROM {table}")
        out.append(_result(i, f"{table} total appointments", expected_totals[key], int(actual)))
    return out


def check_orphans(con):
    """Check 4: every key in a fact exists in its dimension (no orphans)."""
    sql = {
        "booking_wait": "SELECT COUNT(*) FROM fact_appointments_monthly f LEFT JOIN dim_booking_wait d USING (booking_wait) WHERE d.booking_wait IS NULL",
        "duration_band": "SELECT COUNT(*) FROM fact_appointments_by_duration f LEFT JOIN dim_duration_band d ON f.duration_band = d.duration_band WHERE d.duration_band IS NULL",
        "national_category": "SELECT COUNT(*) FROM fact_appointments_by_category f LEFT JOIN dim_national_category d USING (national_category) WHERE d.national_category IS NULL",
        "icb_code": "SELECT COUNT(*) FROM fact_appointments_monthly f LEFT JOIN v_icb d USING (icb_code) WHERE d.icb_code IS NULL",
        "duration sub_icb": "SELECT COUNT(*) FROM fact_appointments_by_duration f LEFT JOIN dim_geography d USING (sub_icb_code) WHERE d.sub_icb_code IS NULL",
        "month_start": "SELECT COUNT(*) FROM (SELECT month_start FROM fact_appointments_monthly UNION ALL SELECT month_start FROM fact_appointments_by_category UNION ALL SELECT month_start FROM fact_appointments_by_duration) f LEFT JOIN dim_date d ON f.month_start = d.date WHERE d.date IS NULL",
    }
    counts = {k: _one(con, q) for k, q in sql.items()}
    return _result(4, "no orphan keys in the facts", 0, sum(counts.values()), json.dumps(counts))


def check_category_geography(con):
    """Check 5: sub-ICB codes taken from the category file exist in dim_geography."""
    bad = _one(con, "SELECT COUNT(DISTINCT f.sub_icb_code) FROM fact_appointments_by_category f "
                    "LEFT JOIN dim_geography d USING (sub_icb_code) WHERE d.sub_icb_code IS NULL")
    return _result(5, "category sub-ICB codes all in dim_geography", 0, bad)


def check_dim_date(con):
    """Check 6: dim_date has exactly one row per calendar day, no gaps or repeats."""
    start, end = config.DATE_RANGE
    expected = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
    rows = _one(con, "SELECT COUNT(*) FROM dim_date")
    distinct = _one(con, "SELECT COUNT(DISTINCT date) FROM dim_date")
    return _result(6, "dim_date has one row per day", expected, rows,
                   f"distinct dates={distinct}", ok=(rows == expected and distinct == expected))


def check_band_labels(con):
    """Check 7: dimensions hold exactly the known label sets, no stray spellings."""
    wait = {r[0] for r in con.execute("SELECT booking_wait FROM dim_booking_wait").fetchall()}
    dur = {r[0] for r in con.execute("SELECT duration_band FROM dim_duration_band").fetchall()}
    exp_wait = {b for b, _ in config.BOOKING_WAIT_BANDS}
    exp_dur = {b for b, _ in config.DURATION_BANDS}
    used_wait = {r[0] for r in con.execute("SELECT DISTINCT booking_wait FROM fact_appointments_monthly").fetchall()}
    used_dur = {r[0] for r in con.execute("SELECT DISTINCT duration_band FROM fact_appointments_by_duration").fetchall()}
    stray = sorted((used_wait - exp_wait) | (used_dur - exp_dur))
    ok = wait == exp_wait and dur == exp_dur and not stray
    return _result(7, "band labels are the known sets", [], stray, "", ok=ok)


def _window_total(con, table):
    lo, hi = config.RECON_WINDOW
    return int(_one(con, f"SELECT COALESCE(SUM(count_of_appointments), 0) FROM {table} "
                         "WHERE month_start BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)", [lo, hi]))


def check_reconciliation(con):
    """Check 8: regional and categories agree, but only where both files have data."""
    reg = _window_total(con, FACTS["regional"])
    cat = _window_total(con, FACTS["categories"])
    return _result(8, "regional equals categories (Aug 2021 to Jun 2022 only)", reg, cat,
                   f"window={config.RECON_WINDOW[0]}..{config.RECON_WINDOW[1]}")


def check_duration_coverage(con):
    """Check 9: duration is a partial file. Over the months BOTH files have, it must cover
    most of categories and never more. (Duration starts later than categories, so comparing
    all months would be wrong.) The reason for the gap is in docs/decision_log.md."""
    lo, hi = config.RECON_WINDOW
    months = "SELECT DISTINCT month_start FROM fact_appointments_by_duration"
    def total(table):
        return int(_one(con, f"SELECT COALESCE(SUM(count_of_appointments), 0) FROM {table} "
                             f"WHERE month_start BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) "
                             f"AND month_start IN ({months})", [lo, hi]))
    dur, cat = total(FACTS["duration"]), total(FACTS["categories"])
    n_months = _one(con, f"SELECT COUNT(*) FROM ({months}) WHERE month_start BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)", [lo, hi])
    ratio = dur / cat if cat else 0.0
    ok = n_months > 0 and config.MIN_DURATION_COVERAGE <= ratio <= 1.0
    return _result(9, "duration covers 90 to 100% of categories (shared months)", f">={config.MIN_DURATION_COVERAGE:.2f}",
                   round(ratio, 4), f"months={n_months} duration={dur:,} categories={cat:,}", ok=ok)


def run_checks(con, expected_totals=None):
    expected_totals = expected_totals or config.EXPECTED_TOTALS
    results = []
    results += check_totals(con, expected_totals)
    for fn in (check_orphans, check_category_geography, check_dim_date, check_band_labels,
               check_reconciliation, check_duration_coverage):
        results.append(fn(con))
    return results


def run(warehouse: Path = config.WAREHOUSE, report_path: Path = config.QUALITY_REPORT,
        expected_totals=None):
    """Run all nine checks, write the JSON report, return (all_passed, results)."""
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        results = run_checks(con, expected_totals)
    finally:
        con.close()
    all_passed = all(r["passed"] for r in results)
    for r in results:
        log.log(logging.INFO if r["passed"] else logging.ERROR, "check %s %s | %s | expected=%s actual=%s %s",
                r["id"], "PASS" if r["passed"] else "FAIL", r["name"], r["expected"], r["actual"], r["detail"])
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "all_passed": all_passed, "checks": results}, indent=2, default=str))
    return all_passed, results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ok, _ = run()
    sys.exit(config.EXIT_OK if ok else config.EXIT_CHECK_FAILED)
