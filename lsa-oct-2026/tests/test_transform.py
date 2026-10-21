"""One test per cleaning rule. Each guards a rule from the Week 2 brief; see
docs/decision_log.md for how each was deliberately broken to prove it can fail."""
import re
from pathlib import Path

import pytest
from pyspark.sql import functions as F

import config
from src import transform

COUNT = "count_of_appointments"


def ds(spark, clean, name):
    return spark.read.parquet(str(clean / name))


def total(df):
    return df.agg(F.sum(COUNT)).first()[0]


# ---- 1. nothing lost: totals before == after, for every dataset
@pytest.mark.parametrize("name", ["regional", "categories", "duration"])
def test_totals_preserved(spark, clean, raw_pd, name):
    assert total(ds(spark, clean, name)) == int(raw_pd[name][COUNT].sum())


# ---- 2. row counts
def test_regional_rows_collapse_but_others_keep_every_row(spark, clean, raw_pd):
    keys = [c for c in raw_pd["regional"].columns if c != COUNT]
    tidy_keys = raw_pd["regional"][keys].apply(lambda s: s.str.replace(r"\s+", " ", regex=True).str.strip())
    tidy_keys["hcp_type"] = tidy_keys["hcp_type"].replace("Other Practice staff", "Other Practice Staff")
    assert ds(spark, clean, "regional").count() == len(tidy_keys.drop_duplicates())
    assert ds(spark, clean, "categories").count() == len(raw_pd["categories"])
    assert ds(spark, clean, "duration").count() == len(raw_pd["duration"])


def test_official_numbers_from_the_brief(spark, clean, is_real):
    if not is_real:
        pytest.skip("brief's numbers only apply to the real NHS files")
    assert ds(spark, clean, "regional").count() == config.EXPECTED_REGIONAL_ROWS_AFTER_SUM
    for name, want in config.EXPECTED_TOTALS.items():
        assert total(ds(spark, clean, name)) == want


# ---- 3. unique keys after summing look-alikes (trap 4)
def test_regional_keys_are_unique(spark, clean):
    df = ds(spark, clean, "regional")
    keys = [c for c in df.columns if c != COUNT]
    assert df.groupBy(*keys).count().filter("count > 1").count() == 0


def test_look_alike_rows_were_summed_not_dropped(spark, clean, raw_pd):
    """If rows were dropped instead of summed the total would be lower than raw."""
    assert total(ds(spark, clean, "regional")) == int(raw_pd["regional"][COUNT].sum())


# ---- 4. tidy labels (trap 5)
@pytest.mark.parametrize("name", ["regional", "categories", "duration"])
def test_no_double_or_edge_spaces_in_any_text_column(spark, clean, name):
    df = ds(spark, clean, name)
    for c, t in df.dtypes:
        if t == "string":
            bad = df.filter(F.col(c).rlike(r"\s{2,}|^\s|\s$")).count()
            assert bad == 0, f"{name}.{c} still has untidy whitespace"


def test_one_spelling_of_other_practice_staff(spark, clean):
    vals = {r[0] for r in ds(spark, clean, "regional").select("hcp_type").distinct().collect()}
    assert "Other Practice staff" not in vals


# ---- 5. hidden BOM (trap 2)
def test_no_byte_order_mark_in_any_column_name(spark, clean):
    for name in ["regional", "categories", "duration"]:
        assert not any("﻿" in c for c in ds(spark, clean, name).columns)
    assert "appointment_date" in ds(spark, clean, "categories").columns


# ---- 6. day-first dates (trap 3)
def test_parse_day_first_unit(spark):
    row = spark.createDataFrame([("02/08/2021",), ("25/08/2021",)], ["d"]).select(
        transform.parse_day_first("d").alias("x")).collect()
    assert str(row[0][0]) == "2021-08-02"       # 2 August, NOT 8 February
    assert str(row[1][0]) == "2021-08-25"


def test_categories_dates_are_day_first(spark, clean):
    df = ds(spark, clean, "categories")
    wrong = df.filter(F.trunc("appointment_day", "month") != F.col("month_start")).count()
    assert wrong == 0, "month of appointment_date must equal appointment_month"
    assert df.filter(F.col("appointment_day").isNull()).count() == 0


# ---- 7. sub-ICB code from the location name
def test_sub_icb_code_taken_from_end_of_name(spark, clean):
    df = ds(spark, clean, "categories")
    assert df.filter(~F.col("sub_icb_code").rlike(r"^[0-9A-Z]{3,5}$")).count() == 0
    assert df.filter(~F.col("sub_icb_location_name").endswith(F.concat(F.lit("- "), F.col("sub_icb_code")))).count() == 0


# ---- 8. counts positive, whole numbers, originals kept beside new columns
@pytest.mark.parametrize("name", ["regional", "categories", "duration"])
def test_counts_are_positive_whole_numbers(spark, clean, name):
    df = ds(spark, clean, name)
    assert dict(df.dtypes)[COUNT] == "bigint"
    assert df.filter(F.col(COUNT) <= 0).count() == 0


def test_original_columns_kept_beside_new_ones(spark, clean):
    cols = ds(spark, clean, "categories").columns
    assert {"appointment_date", "appointment_month", "appointment_day", "month_start", "sub_icb_code"} <= set(cols)


# ---- 9. partitioned by month
@pytest.mark.parametrize("name", ["regional", "categories", "duration"])
def test_parquet_is_partitioned_by_month(spark, clean, name):
    parts = [p.name for p in (clean / name).iterdir() if p.name.startswith("month_start=")]
    assert parts and len(parts) == ds(spark, clean, name).select("month_start").distinct().count()


# ---- 10. idempotent: a second run gives identical results
def test_second_run_is_identical(spark, raw_dir, clean, tmp_path):
    transform.run(raw_dir, tmp_path, spark=spark, expected_totals=None, expected_regional_rows=None)
    for name in ["regional", "categories", "duration"]:
        a, b = ds(spark, clean, name), ds(spark, tmp_path, name)
        assert (a.count(), total(a)) == (b.count(), total(b))
        assert a.exceptAll(b.select(*a.columns)).count() == 0
