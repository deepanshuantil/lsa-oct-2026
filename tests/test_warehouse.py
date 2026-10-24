"""Week 3 tests: the loaded DuckDB warehouse, the quality checks and the pipeline exit codes.

Each 'can fail' test breaks something on purpose and proves the safety net catches it.
"""
import shutil

import duckdb
import pytest

import config
import run_pipeline
from src import checks, load

FACTS = ["fact_appointments_monthly", "fact_appointments_by_category", "fact_appointments_by_duration"]
DIMS = ["dim_date", "dim_booking_wait", "dim_duration_band", "dim_geography", "dim_national_category"]


def snapshot(con):
    """Row count and total of every fact plus row counts of every dimension."""
    out = {t: con.execute(f"SELECT COUNT(*), SUM(count_of_appointments) FROM {t}").fetchone() for t in FACTS}
    out.update({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in DIMS})
    return out


def test_all_eight_tables_exist(con):
    names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables "
                                       "WHERE table_type = 'BASE TABLE'").fetchall()}
    assert set(FACTS + DIMS) <= names


def test_fact_totals_equal_expected_constants(con, expected_totals):
    got = {k: int(con.execute(f"SELECT SUM(count_of_appointments) FROM {t}").fetchone()[0])
           for k, t in checks.FACTS.items()}
    assert got == expected_totals


def test_warehouse_matches_transform_output(con, clean, spark):
    """The load must not change a single appointment on the way in."""
    from pyspark.sql import functions as F
    for key, table in checks.FACTS.items():
        spark_total = spark.read.parquet(str(clean / key)).agg(F.sum("count_of_appointments")).first()[0]
        assert con.execute(f"SELECT SUM(count_of_appointments) FROM {table}").fetchone()[0] == spark_total


def test_no_orphan_keys(con):
    assert checks.check_orphans(con)["passed"]


def test_category_codes_exist_in_geography(con):
    assert checks.check_category_geography(con)["passed"]


def test_band_labels_are_in_dimensions(con):
    assert checks.check_band_labels(con)["passed"]


def test_dim_date_one_row_per_day(con):
    assert checks.check_dim_date(con)["passed"]


def test_dimension_keys_are_unique(con):
    for table, col in [("dim_geography", "sub_icb_code"), ("dim_national_category", "national_category"),
                       ("dim_booking_wait", "booking_wait"), ("dim_duration_band", "duration_band"),
                       ("dim_date", "date")]:
        assert con.execute(f"SELECT COUNT(*) - COUNT(DISTINCT {col}) FROM {table}").fetchone()[0] == 0, table


def test_geography_row_count(con, is_real):
    if is_real:
        assert con.execute("SELECT COUNT(*) FROM dim_geography").fetchone()[0] == config.EXPECTED_GEOGRAPHY_ROWS


def test_all_nine_checks_pass_on_good_data(con, expected_totals):
    results = checks.run_checks(con, expected_totals)
    assert len(results) == 9
    assert [r["id"] for r in results if not r["passed"]] == []


def test_reconciliation_and_coverage(con):
    assert checks.check_reconciliation(con)["passed"]
    assert checks.check_duration_coverage(con)["passed"]


def test_reload_twice_changes_nothing(clean, warehouse, expected_geo, tmp_path):
    copy = tmp_path / "w.duckdb"
    shutil.copy2(warehouse, copy)
    c = duckdb.connect(str(copy)); before = snapshot(c); c.close()
    load.run(clean, copy, expected_geography_rows=expected_geo)
    load.run(clean, copy, expected_geography_rows=expected_geo)
    c = duckdb.connect(str(copy)); after = snapshot(c); c.close()
    assert after == before


def test_failed_month_load_rolls_back(clean, warehouse, tmp_path):
    """If the insert breaks half way, the month must be exactly as it was (no half-loaded data)."""
    copy = tmp_path / "w.duckdb"
    shutil.copy2(warehouse, copy)
    c = duckdb.connect(str(copy))
    table = "fact_appointments_monthly"
    month = c.execute(f"SELECT MIN(month_start) FROM {table}").fetchone()[0]
    before = c.execute(f"SELECT COUNT(*), SUM(count_of_appointments) FROM {table}").fetchone()
    with pytest.raises(Exception):
        load.replace_month(c, table, "SELECT CAST('not a date' AS DATE), 'x', 'x', 'x', 'x', 'x', 1", month)
    assert c.execute(f"SELECT COUNT(*), SUM(count_of_appointments) FROM {table}").fetchone() == before
    c.close()


# --------------------------------------------------------------- deliberately broken inputs
@pytest.fixture()
def broken(warehouse, tmp_path):
    copy = tmp_path / "broken.duckdb"
    shutil.copy2(warehouse, copy)
    c = duckdb.connect(str(copy))
    yield c
    c.close()


def failed_ids(c, expected_totals):
    return {r["id"] for r in checks.run_checks(c, expected_totals) if not r["passed"]}


def test_lost_rows_fail_the_total_check(broken, expected_totals):
    broken.execute("DELETE FROM fact_appointments_by_duration WHERE rowid IN "
                   "(SELECT rowid FROM fact_appointments_by_duration LIMIT 1)")
    assert 3 in failed_ids(broken, expected_totals)


def test_orphan_row_fails_the_orphan_check(broken, expected_totals):
    broken.execute("UPDATE fact_appointments_by_duration SET duration_band = 'Bogus' WHERE rowid IN "
                   "(SELECT rowid FROM fact_appointments_by_duration LIMIT 1)")
    assert {4, 7} & failed_ids(broken, expected_totals)


def test_gap_in_dim_date_fails(broken, expected_totals):
    broken.execute("DELETE FROM dim_date WHERE date = DATE '2021-12-01'")
    assert 6 in failed_ids(broken, expected_totals)


def test_double_counted_facts_fail_reconciliation(broken, expected_totals):
    broken.execute("INSERT INTO fact_appointments_by_category SELECT * FROM fact_appointments_by_category")
    ids = failed_ids(broken, expected_totals)
    assert 2 in ids and 8 in ids


def test_duration_above_categories_fails_coverage(broken, expected_totals):
    broken.execute("UPDATE fact_appointments_by_duration SET count_of_appointments = count_of_appointments * 2")
    assert 9 in failed_ids(broken, expected_totals)


def test_failed_check_gives_exit_code_2_and_leaves_warehouse_alone(clean, warehouse, tmp_path, expected_totals):
    """A wrong expected total must stop the run: exit code 2, real warehouse byte-for-byte unchanged."""
    target = tmp_path / "w.duckdb"
    shutil.copy2(warehouse, target)
    before = target.read_bytes()
    wrong = dict(expected_totals, regional=expected_totals["regional"] + 1)
    import logging
    code = run_pipeline.staged_load_and_check(clean, target, tmp_path / "report.json", wrong, None,
                                              logging.getLogger("test"))
    assert code == config.EXIT_CHECK_FAILED
    assert target.read_bytes() == before
    assert not target.with_name(target.name + ".staging").exists()
    assert '"all_passed": false' in (tmp_path / "report.json").read_text()


def test_duration_starts_later_than_categories_but_check_still_passes(con):
    """Real files: duration has fewer months than categories. The coverage check must compare
    shared months only; comparing all months would give a false failure (it did, at 57%)."""
    n_dur = con.execute("SELECT COUNT(DISTINCT month_start) FROM fact_appointments_by_duration").fetchone()[0]
    n_cat = con.execute("SELECT COUNT(DISTINCT month_start) FROM fact_appointments_by_category").fetchone()[0]
    assert n_dur < n_cat
    assert checks.check_duration_coverage(con)["passed"]
