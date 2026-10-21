# GP Appointments ETL: LSA Data Engineering Internship, October 2026

An end-to-end pipeline for NHS England GP appointment data: extract, transform (PySpark), load (DuckDB), dashboard (Streamlit).

**The code, tests and documentation are in the [`lsa-oct-2026`](lsa-oct-2026/) folder.** Start with [its README](lsa-oct-2026/README.md).

## Status
- [x] Week 1: Extract and data profile
- [x] Week 2: Transform and tests (PySpark)
- [ ] Week 3: Load and quality checks (DuckDB)
- [ ] Week 4: Dashboard (Streamlit)

## Week 2 results (real data)
- Regional: 596,821 rows -> 295,692, total 742,804,525
- Categories: total 296,046,770
- Duration: total 167,980,692
- A second run gives identical results
- Storage: source CSVs 159 MB -> clean Parquet 5.6 MB
- Tests: 23 passed

Source: NHS England, Appointments in General Practice. Not an official NHS product.
