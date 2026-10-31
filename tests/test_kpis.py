"""Week 4 tests: the KPI export and the dashboard.

The sample warehouse (conftest.py) is built from sample data whose totals we know,
so we can check the exported counts against the warehouse, and that the dashboard runs without errors.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import kpis  # noqa: E402


@pytest.fixture()
def exported(warehouse, tmp_path):
    kpis.run(warehouse, tmp_path)
    return tmp_path


def test_all_tables_written(exported):
    for name in kpis.QUERIES:
        assert (exported / f"{name}.csv").exists()


def test_monthly_totals_match_warehouse(exported, con):
    exported_total = pd.read_csv(exported / "monthly_totals.csv")["appointments"].sum()
    warehouse_total = con.execute("SELECT SUM(count_of_appointments) FROM fact_appointments_monthly").fetchone()[0]
    assert exported_total == warehouse_total


def test_missing_last_year_is_blank_not_zero(exported):
    """A month with no prior year must be blank. Zero would make a false -100% change."""
    df = pd.read_csv(exported / "monthly_totals.csv")
    first_year = df[df["month_start"] == df["month_start"].min()]
    assert first_year["appointments_last_year"].isna().all()


def test_known_never_exceeds_total(exported):
    wait = pd.read_csv(exported / "wait_monthly.csv")
    assert (wait["same_day"] <= wait["known_wait"]).all()
    assert (wait["long_wait"] <= wait["known_wait"]).all()


def test_dashboard_runs_without_errors(exported, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("KPI_DIR", str(exported))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs) == 6


def test_dashboard_shows_friendly_error_when_data_missing(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("KPI_DIR", str(tmp_path))
    at = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=60).run()
    assert not at.exception
    assert len(at.error) == 1
