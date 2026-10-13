# GP Appointments ETL: LSA Data Engineering Internship, October 2026

An end-to-end data pipeline for NHS England GP appointment data: **extract** the raw files, **transform** them with PySpark, **load** them into a DuckDB star schema, and show the results in a Streamlit dashboard.

**The question it answers:** How is GP appointment capacity being used, and where is it being lost?

**Author:** Deepanshu

## Status

- [x] Week 1: Extract and data profile
- [ ] Week 2: Transform and tests (PySpark)
- [ ] Week 3: Load and quality checks (DuckDB)
- [ ] Week 4: Dashboard (Streamlit)

## Data

Source: NHS England, *Appointments in General Practice* (digital.nhs.uk).

| File | What one row is |
| --- | --- |
| appointments_regional.csv | Appointments for one ICB, month, status, staff type, mode and booking wait |
| national_categories.csv | Appointments for one sub-ICB location, day, service setting and national category |
| actual_duration.csv.xlsx | Appointments for one sub-ICB location, day and consultation-length band |

The data files are **not** stored in this repository. `data/raw/manifest.json` (created by the extract step) records exactly which files were used.

The data is aggregated counts with no patient-level records. This is not an official NHS product.

## How to run

1. Install Java 17, 21 or 25, and Python 3.10 or newer.
2. Install the requirements: `pip install -r requirements.txt`
3. Put the three data files in a folder and point the extract script at it.
4. Run the extract step: `python src/extract.py`

(The full pipeline will run with `python run_pipeline.py` once Weeks 2 and 3 are built.)

## Project structure

```
lsa-oct-2026/
  README.md
  requirements.txt
  data/raw/         original files, never edited (not committed)
  data/clean/       Parquet output of the transform (not committed)
  warehouse/        DuckDB file (not committed)
  src/              extract.py, transform.py, load.py, checks.py
  run_pipeline.py   runs all four stages in order
  tests/            pytest tests
  docs/             data profile, decision log, quality report
  app/              Streamlit dashboard
```

## Source credit

Source: NHS England, Appointments in General Practice.
