# GP Appointments ETL: LSA Data Engineering Internship, October 2026

An end-to-end pipeline for NHS England GP appointment data: extract, transform (PySpark), load (DuckDB), dashboard (Streamlit).

**Author:** Deepanshu Deepanshu

## Status
- [x] Week 1: Extract and data profile
- [x] Week 2: Transform and tests (PySpark)
- [ ] Week 3: Load and quality checks (DuckDB)
- [ ] Week 4: Dashboard (Streamlit)

## How to run
1. Install Java 17, 21 or 25 and Python 3.10+.
2. `pip install -r requirements.txt`
3. Put the three NHS files in a folder and set `LSA_SOURCE` to it.
4. `python run_pipeline.py` runs extract and transform.
5. `python -m pytest tests -q` runs the tests.

## Results (real data)
- Regional: 596,821 rows -> 295,692, total 742,804,525
- Categories: total 296,046,770
- Duration: total 167,980,692
- A second run gives identical results.
- Storage: source CSVs 159 MB -> clean Parquet 5.6 MB
- Tests: 26 passed

## Documentation
- `docs/decision_log.md`: every change to the data and why
- `docs/star_schema.md`: the warehouse design (built in Week 3)

Source: NHS England, Appointments in General Practice. Not an official NHS product.
