"""Transform stage (PySpark): raw CSVs -> clean Parquet, partitioned by month.

Rules (from the Week 2 brief):
  * explicit schemas, never inferSchema
  * the five traps fixed in code (raw is never touched)
  * counts stay whole numbers; new columns sit BESIDE the originals
  * nothing is lost: totals are checked before and after every step
"""
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

log = logging.getLogger("transform")

COUNT = "count_of_appointments"


def _schema(text_cols: list[str]) -> StructType:
    return StructType([StructField(c, StringType(), True) for c in text_cols]
                      + [StructField(COUNT, LongType(), True)])


REGIONAL_SCHEMA = _schema(["icb_ons_code", "appointment_month", "appointment_status", "hcp_type",
                           "appointment_mode", "time_between_book_and_appointment"])
CATEGORIES_SCHEMA = _schema(["appointment_date", "icb_ons_code", "sub_icb_location_name", "service_setting",
                             "context_type", "national_category"])
# categories file has the count in the 7th place, then appointment_month last
CATEGORIES_SCHEMA = StructType(CATEGORIES_SCHEMA.fields + [StructField("appointment_month", StringType(), True)])
DURATION_SCHEMA = StructType([StructField(c, StringType(), True) for c in
                              ["sub_icb_location_code", "sub_icb_location_ons_code", "sub_icb_location_name",
                               "icb_ons_code", "region_ons_code", "appointment_date", "actual_duration"]]
                             + [StructField(COUNT, LongType(), True)])

# Formats we accept for MONTH columns whose text layout the profile did not pin down.
MONTH_FORMATS = ["yyyy-MM-dd", "yyyy-MM-dd HH:mm:ss", "dd/MM/yyyy", "MMM-yy", "MMMyyyy", "MMM-yyyy",
                 "MMM yyyy", "yyyy-MM"]


# ------------------------------------------------------------------ helpers
def get_spark() -> SparkSession:
    spark = (SparkSession.builder.appName("lsa-transform").master("local[*]")
             .config("spark.sql.shuffle.partitions", str(config.SHUFFLE_PARTITIONS))
             .config("spark.driver.memory", "4g").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark


def tidy(col: str) -> F.Column:
    """Trim and collapse runs of whitespace: '15  to 21 Days' -> '15 to 21 Days'."""
    return F.trim(F.regexp_replace(F.col(col), r"\s+", " "))


def parse_day_first(col: str) -> F.Column:
    """Trap 3: day-first dates. State the format; never let Spark guess.
    Under Spark 4's ANSI mode a value that does not fit raises an error (loud)."""
    return F.to_date(F.col(col), "dd/MM/yyyy")


def parse_any(col: str, formats: list[str] = MONTH_FORMATS) -> F.Column:
    """First format that fits wins; a value no format fits becomes null."""
    def one(f: str) -> F.Column:
        d = F.expr(f"try_to_timestamp(`{col}`, '{f}')").cast("date")
        return F.when(F.year(d).between(1990, 2100), d)     # '2020' misread as year 0020 -> next format
    return F.coalesce(*[one(f) for f in formats])


def read_csv(spark: SparkSession, path: Path, schema: StructType) -> DataFrame:
    """Read with an explicit schema after checking the header (BOM stripped) matches it."""
    with open(path, encoding="utf-8", newline="") as f:
        header = f.readline().strip("\r\n")
    cols = [c.replace("﻿", "").strip().strip('"') for c in header.split(",")]   # trap 2: BOM
    if cols != schema.names:
        raise ValueError(f"{path.name}: header {cols} does not match expected schema {schema.names}")
    return spark.read.csv(str(path), header=True, schema=schema, mode="FAILFAST", encoding="UTF-8")


def total(df: DataFrame) -> int:
    return int(df.agg(F.sum(COUNT)).first()[0])


def check_equal(step: str, before, after) -> None:
    if before != after:
        raise AssertionError(f"{step}: changed from {before:,} to {after:,}")
    log.info("%s | unchanged: %s", step, f"{after:,}")


def write(df: DataFrame, out: Path) -> None:
    df.write.mode("overwrite").partitionBy("month_start").parquet(str(out))   # overwrite = idempotent


# ------------------------------------------------------------------ datasets
def transform_regional(spark, raw: Path, out: Path) -> dict:
    df = read_csv(spark, raw, REGIONAL_SCHEMA)
    rows_in, total_in = df.count(), total(df)
    log.info("regional | read rows=%s total=%s", f"{rows_in:,}", f"{total_in:,}")

    # Trap 5: tidy labels, one spelling of Other Practice Staff
    for c in [f.name for f in REGIONAL_SCHEMA if f.dataType == StringType()]:
        df = df.withColumn(c, tidy(c))
    df = df.withColumn("hcp_type", F.when(F.lower(F.col("hcp_type")) == "other practice staff",
                                          F.lit("Other Practice Staff")).otherwise(F.col("hcp_type")))
    df = df.withColumn("month_start", F.trunc(parse_any("appointment_month"), "month"))   # new column
    if df.filter(F.col("month_start").isNull()).count():
        raise ValueError("regional: appointment_month could not be parsed; check the raw format")
    check_equal("regional | after tidy (total)", total_in, total(df))

    # Trap 4: sum look-alike rows, never drop them
    keys = [c for c in df.columns if c != COUNT]
    df = df.groupBy(*keys).agg(F.sum(COUNT).alias(COUNT))
    rows_out, total_out = df.count(), total(df)
    check_equal("regional | after summing look-alikes (total)", total_in, total_out)
    log.info("regional | rows %s -> %s (%s merged)", f"{rows_in:,}", f"{rows_out:,}", f"{rows_in - rows_out:,}")
    write(df, out)
    return {"rows_in": rows_in, "rows_out": rows_out, "total_in": total_in, "total_out": total_out}


def transform_categories(spark, raw: Path, out: Path) -> dict:
    df = read_csv(spark, raw, CATEGORIES_SCHEMA)
    rows_in, total_in = df.count(), total(df)
    log.info("categories | read rows=%s total=%s", f"{rows_in:,}", f"{total_in:,}")
    for c in [f.name for f in CATEGORIES_SCHEMA if f.dataType == StringType() and f.name != "appointment_date"]:
        df = df.withColumn(c, tidy(c))
    df = (df.withColumn("appointment_day", parse_day_first("appointment_date"))          # new column
            .withColumn("month_start", F.trunc(parse_any("appointment_month"), "month"))
            .withColumn("sub_icb_code", F.regexp_extract(F.col("sub_icb_location_name"), r"-\s*([0-9A-Z]{3})\s*$", 1)))
    if df.filter(F.col("month_start").isNull() | (F.col("sub_icb_code") == "")).count():
        raise ValueError("categories: could not parse appointment_month or the sub-ICB code")
    check_equal("categories | after transform (total)", total_in, total(df))
    write(df, out)
    return {"rows_in": rows_in, "rows_out": df.count(), "total_in": total_in, "total_out": total(df)}


def transform_duration(spark, raw: Path, out: Path) -> dict:
    df = read_csv(spark, raw, DURATION_SCHEMA)
    rows_in, total_in = df.count(), total(df)
    log.info("duration | read rows=%s total=%s", f"{rows_in:,}", f"{total_in:,}")
    for c in [f.name for f in DURATION_SCHEMA if f.dataType == StringType()]:
        df = df.withColumn(c, tidy(c))
    df = df.withColumn("appointment_day", parse_any("appointment_date"))
    df = df.withColumn("month_start", F.trunc("appointment_day", "month"))
    if df.filter(F.col("month_start").isNull()).count():
        raise ValueError("duration: appointment_date could not be parsed; check the converted CSV")
    check_equal("duration | after transform (total)", total_in, total(df))
    write(df, out)
    return {"rows_in": rows_in, "rows_out": df.count(), "total_in": total_in, "total_out": total(df)}


# ------------------------------------------------------------------ entry point
def run(raw_dir: Path = config.RAW, clean_dir: Path = config.CLEAN, spark: SparkSession | None = None,
        expected_totals: dict | None = config.EXPECTED_TOTALS,
        expected_regional_rows: int | None = config.EXPECTED_REGIONAL_ROWS_AFTER_SUM) -> dict:
    """Transform all three datasets. Returns {dataset name: output folder}."""
    raw_dir, clean_dir = Path(raw_dir), Path(clean_dir)
    own = spark is None
    spark = spark or get_spark()
    t0 = datetime.now(timezone.utc)
    log.info("transform start | raw=%s clean=%s", raw_dir, clean_dir)
    try:
        outs = {config.CLEAN_REGIONAL: clean_dir / config.CLEAN_REGIONAL,
                config.CLEAN_CATEGORIES: clean_dir / config.CLEAN_CATEGORIES,
                config.CLEAN_DURATION: clean_dir / config.CLEAN_DURATION}
        stats = {
            config.CLEAN_REGIONAL: transform_regional(spark, raw_dir / config.REGIONAL_CSV, outs[config.CLEAN_REGIONAL]),
            config.CLEAN_CATEGORIES: transform_categories(spark, raw_dir / config.CATEGORIES_CSV, outs[config.CLEAN_CATEGORIES]),
            config.CLEAN_DURATION: transform_duration(spark, raw_dir / config.DURATION_CSV, outs[config.CLEAN_DURATION]),
        }
        if expected_totals is not None:
            for name, want in expected_totals.items():
                got = stats[name]["total_out"]
                if got != want:
                    raise AssertionError(f"{name}: total {got:,} != brief's {want:,}")
        if expected_regional_rows is not None and stats[config.CLEAN_REGIONAL]["rows_out"] != expected_regional_rows:
            raise AssertionError(f"regional rows {stats[config.CLEAN_REGIONAL]['rows_out']:,} != {expected_regional_rows:,}")
        log.info("transform done in %.1fs | %s", (datetime.now(timezone.utc) - t0).total_seconds(),
                 {k: (v["rows_out"], v["total_out"]) for k, v in stats.items()})
        return outs
    finally:
        if own:
            spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run()
