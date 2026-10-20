"""Extract stage: copy the three source files into data/raw/, convert the Excel
file to CSV, and write manifest.json. Raw copies are NEVER edited.

    python src/extract.py --source /path/to/original/files
"""
import argparse
import csv
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

log = logging.getLogger("extract")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_rows(path: Path) -> int:
    """Data rows excluding the header. utf-8-sig only changes how we READ."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def _describe(path: Path, rows: int, when: str, **extra) -> dict:
    return {"file_name": path.name, "size_bytes": path.stat().st_size,
            "sha256": sha256_of(path), "row_count": rows, "extracted_at": when, **extra}


def run(source: Path = config.SOURCE, dest: Path = config.RAW,
        expected_rows: dict | None = config.EXPECTED_ROWS) -> dict:
    """Copy, convert and fingerprint the raw files. Returns {name: output path}."""
    source, dest = Path(source), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    log.info("extract start | source=%s dest=%s", source, dest)

    for name in (config.REGIONAL_CSV, config.CATEGORIES_CSV, config.DURATION_XLSX):
        src, dst = source / name, dest / name
        if not src.exists():
            raise FileNotFoundError(f"Missing source file: {src}")
        if src.resolve() != dst.resolve():          # idempotent: re-copy is harmless
            shutil.copy2(src, dst)
        log.info("copied %s", name)

    xlsx, csv_path = dest / config.DURATION_XLSX, dest / config.DURATION_CSV
    df = pd.read_excel(xlsx, sheet_name=0, dtype=str, keep_default_na=False)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    log.info("converted %s -> %s (%s rows)", xlsx.name, csv_path.name, f"{len(df):,}")

    when = started.isoformat(timespec="seconds")
    files = [
        _describe(dest / config.REGIONAL_CSV, count_csv_rows(dest / config.REGIONAL_CSV), when),
        _describe(dest / config.CATEGORIES_CSV, count_csv_rows(dest / config.CATEGORIES_CSV), when),
        _describe(csv_path, count_csv_rows(csv_path), when,
                  converted_from=config.DURATION_XLSX, source_sha256=sha256_of(xlsx)),
    ]
    (dest / config.MANIFEST).write_text(json.dumps({"extracted_at": when, "files": files}, indent=2))

    for e in files:
        log.info("manifest | %s rows=%s bytes=%s", e["file_name"], f"{e['row_count']:,}", f"{e['size_bytes']:,}")
        if expected_rows is not None and e["row_count"] != expected_rows[e["file_name"]]:
            raise ValueError(f"{e['file_name']}: {e['row_count']:,} rows, expected "
                             f"{expected_rows[e['file_name']]:,}")
    log.info("extract done in %.1fs", (datetime.now(timezone.utc) - started).total_seconds())
    return {"regional": dest / config.REGIONAL_CSV, "categories": dest / config.CATEGORIES_CSV,
            "duration": csv_path, "manifest": dest / config.MANIFEST}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(config.SOURCE))
    ap.add_argument("--dest", default=str(config.RAW))
    a = ap.parse_args()
    run(Path(a.source), Path(a.dest))
