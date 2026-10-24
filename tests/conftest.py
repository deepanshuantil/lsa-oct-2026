"""Shared fixtures. The fixture RUNS the transform, so breaking a rule in transform.py
makes the tests fail (tests on stale output would prove nothing).

By default tests use your real data in data/raw. Set LSA_USE_SAMPLE=1 to use the small
fake dataset instead (for laptops without the data, or CI).
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import config  # noqa: E402
from src import extract, transform  # noqa: E402
import make_sample_data  # noqa: E402


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory):
    if os.environ.get("LSA_USE_SAMPLE") == "1":
        src = make_sample_data.build(tmp_path_factory.mktemp("sample_src"))
        raw = tmp_path_factory.mktemp("sample_raw")
        extract.run(src, raw, expected_rows=None)      # also exercises the extract stage
        return raw
    if not (config.RAW / config.DURATION_CSV).exists():
        pytest.skip("no data in data/raw; run extract first or set LSA_USE_SAMPLE=1")
    return config.RAW


@pytest.fixture(scope="session")
def is_real(raw_dir):
    return raw_dir == config.RAW


@pytest.fixture(scope="session")
def spark():
    s = transform.get_spark()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def clean(raw_dir, spark, tmp_path_factory):
    out = tmp_path_factory.mktemp("clean")
    transform.run(raw_dir, out, spark=spark, expected_totals=None, expected_regional_rows=None)
    return out


@pytest.fixture(scope="session")
def raw_pd(raw_dir):
    """Independent view of the raw files (pandas), used for 'before' numbers."""
    def rd(name):
        return pd.read_csv(raw_dir / name, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    out = {k: rd(f) for k, f in [("regional", config.REGIONAL_CSV), ("categories", config.CATEGORIES_CSV),
                                  ("duration", config.DURATION_CSV)]}
    for df in out.values():
        df["count_of_appointments"] = df["count_of_appointments"].astype("int64")
    return out
