"""Runs the pipeline stages in order and stops at the first failure.

    python run_pipeline.py                      # source = data/raw (or $LSA_SOURCE)
    python run_pipeline.py --source /path/to/original/files
    python run_pipeline.py --sample             # tiny fake data, no NHS files needed

Order: extract -> transform -> load -> checks. The load goes into a STAGING copy of the
warehouse; only if all nine checks pass is it swapped in. Exit codes:
    0  loaded and every check passed
    2  a quality check failed (the real warehouse was not touched)
    1  something crashed

Safe to rerun: every stage overwrites its own output, and the load replaces whole months.
"""
import argparse
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import config
import pandas as pd

from src import checks, extract, load, transform


def setup_logging() -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.LOGS / "pipeline.log")])


def raw_totals(raw: Path) -> dict:
    """Sample mode only: expected totals read straight from the raw CSVs with pandas, so they
    do not depend on Spark or DuckDB. (Real runs use the constants in config.py.)"""
    col = "count_of_appointments"
    return {k: int(pd.read_csv(raw / f, usecols=[col], encoding="utf-8-sig")[col].sum())
            for k, f in (("regional", config.REGIONAL_CSV), ("categories", config.CATEGORIES_CSV),
                         ("duration", config.DURATION_CSV))}


def staged_load_and_check(clean, warehouse, report, expected_totals, expected_geo, log) -> int:
    """Load into warehouse.staging, check it, and swap it in only if every check passed."""
    warehouse = Path(warehouse)
    staging = warehouse.with_name(warehouse.name + ".staging")
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    for leftover in (staging, staging.with_name(staging.name + ".wal")):
        leftover.unlink(missing_ok=True)
    if warehouse.exists():
        shutil.copy2(warehouse, staging)          # start from the current state: idempotent per month
    load.run(clean, staging, expected_geography_rows=expected_geo)
    ok, results = checks.run(staging, report, expected_totals)
    if not ok:
        staging.unlink(missing_ok=True)
        failed = [r["id"] for r in results if not r["passed"]]
        log.error("QUALITY CHECK FAILED (checks %s): warehouse left unchanged. See %s", failed, report)
        return config.EXIT_CHECK_FAILED
    os.replace(staging, warehouse)
    log.info("all %d checks passed: warehouse updated at %s", len(results), warehouse)
    return config.EXIT_OK


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(config.SOURCE), help="folder with the original NHS files")
    ap.add_argument("--sample", action="store_true", help="use small fake data (no brief totals checked)")
    args = ap.parse_args()
    setup_logging()
    log = logging.getLogger("pipeline")

    source, raw, clean = Path(args.source), config.RAW, config.CLEAN
    expected_rows, expected_totals, expected_reg = (config.EXPECTED_ROWS, config.EXPECTED_TOTALS,
                                                   config.EXPECTED_REGIONAL_ROWS_AFTER_SUM)
    warehouse, report, expected_geo = config.WAREHOUSE, config.QUALITY_REPORT, config.EXPECTED_GEOGRAPHY_ROWS
    if args.sample:
        sys.path.insert(0, str(config.ROOT / "tests"))
        import make_sample_data
        tmp = Path(tempfile.mkdtemp())
        source, raw, clean = make_sample_data.build(tmp / "src"), tmp / "raw", tmp / "clean"
        expected_rows = expected_totals = expected_reg = expected_geo = None
        warehouse, report = tmp / "warehouse.duckdb", tmp / "quality_report.json"

    spark = None
    try:
        log.info("=== pipeline start ===")
        paths = extract.run(source, raw, expected_rows=expected_rows)
        spark = transform.get_spark()
        outs = transform.run(raw, clean, spark=spark, expected_totals=expected_totals,
                             expected_regional_rows=expected_reg)
        if args.sample:
            expected_totals = raw_totals(raw)
        spark.stop()                      # free the JVM before loading
        spark = None
        code = staged_load_and_check(clean, warehouse, report, expected_totals, expected_geo, log)
        log.info("=== pipeline finished: exit code %s ===", code)
        return code
    except Exception:
        log.exception("PIPELINE STOPPED: a stage failed (see the error above)")
        return config.EXIT_CRASH
    finally:
        if spark is not None:
            spark.stop()


if __name__ == "__main__":
    sys.exit(main())
