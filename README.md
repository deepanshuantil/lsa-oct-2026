# GP Appointments ETL: LSA Data Engineering Internship, October 2026

An end-to-end pipeline for NHS England GP appointment data: extract, transform (PySpark), load (DuckDB), dashboard (Streamlit).

**Author:** Deepanshu

## Status
- [x] Week 1: Extract and data profile
- [x] Week 2: Transform and tests (PySpark)
- [x] Week 3: Load and quality checks (DuckDB)
- [x] Week 4: Dashboard (Streamlit)

## Live dashboard
https://lsa-oct-2026-hbomywgixrapmwlm7jdieb.streamlit.app/

Twelve measures with a data-quality caveat under every chart. To run it yourself: `streamlit run app/dashboard.py` (the numbers come from the small CSV files in `app/data`, made by `python src/kpis.py`).

## How to run
1. Install Java 17, 21 or 25 and Python 3.10+.
2. `pip install -r requirements.txt`
3. Put the three NHS files in a folder and set `LSA_SOURCE` to it.
4. `python run_pipeline.py` runs extract, transform, load and the nine quality checks.
   Exit codes: 0 loaded and all checks passed, 2 a check failed (warehouse untouched), 1 crashed.
   `python run_pipeline.py --sample` runs the same on small fake data.
5. `python -m pytest tests -q` runs the tests.

## Results (real data)
- Regional: 596,821 rows -> 295,692, total 742,804,525
- Categories: total 296,046,770
- Duration: total 167,980,692
- A second run gives identical results.
- Storage: source CSVs 159 MB -> clean Parquet 5.6 MB
- Warehouse: 3 fact tables and 5 dimensions in `warehouse/warehouse.duckdb` (not in Git); reloading changes nothing
- Quality checks: 9 of 9 pass (`docs/quality_report.json`); duration covers 91.8% of categories over the 7 months both files share
- Tests: 52 passed

## Documentation
- `docs/data_profile.md`: what is in the three source files
- `docs/decision_log.md`: every change to the data and why
- `docs/star_schema.md`: the warehouse design
- `app/caveats.py`: the data-quality caveats shown under every dashboard chart

## Project layout
```
src/        extract, transform (PySpark), load and checks (DuckDB), KPI export
app/        Streamlit dashboard and its small data files
tests/      pytest suite (sample-data generator included)
docs/       profile, decision log, schema, quality report
notebooks/  the Colab notebook used to run Week 2
```

## Known data limits
- About 3% to 10% of appointments have an Unknown status, so attendance rates exclude them.
- The files have no patient population, so there are no per-1,000 rates.
- The regional file ends in June 2022, so year-on-year compares month with month.

Source: NHS England, Appointments in General Practice. Not an official NHS product.
