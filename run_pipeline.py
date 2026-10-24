"""Runs the pipeline stages in order and stops at the first failure.

    python run_pipeline.py                      # source = data/raw (or $LSA_SOURCE)
    python run_pipeline.py --source /path/to/original/files
    python run_pipeline.py --sample             # tiny fake data, no NHS files needed

Safe to rerun: every stage overwrites its own output.
"""
import argparse
import logging
import sys
import tempfile
from pathlib import Path

import config
from src import extract, transform


def setup_logging() -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.LOGS / "pipeline.log")])


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
    if args.sample:
        sys.path.insert(0, str(config.ROOT / "tests"))
        import make_sample_data
        tmp = Path(tempfile.mkdtemp())
        source, raw, clean = make_sample_data.build(tmp / "src"), tmp / "raw", tmp / "clean"
        expected_rows = expected_totals = expected_reg = None

    spark = None
    try:
        log.info("=== pipeline start ===")
        paths = extract.run(source, raw, expected_rows=expected_rows)
        spark = transform.get_spark()
        outs = transform.run(raw, clean, spark=spark, expected_totals=expected_totals,
                             expected_regional_rows=expected_reg)
        log.info("=== pipeline finished OK === clean data in %s", clean)
        return 0
    except Exception:
        log.exception("PIPELINE STOPPED: a stage failed (see the error above)")
        return 1
    finally:
        if spark is not None:
            spark.stop()


if __name__ == "__main__":
    sys.exit(main())
