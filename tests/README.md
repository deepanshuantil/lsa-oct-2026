# Tests

Run with `python -m pytest tests -q` (52 pass on the real data).

| File | Covers |
|------|--------|
| `test_transform.py` | The cleaning rules: totals preserved, dates, look-alike rows, Parquet layout |
| `test_warehouse.py` | The load: star schema, idempotent reload, nine quality checks, exit codes |
| `test_kpis.py` | The dashboard export and the dashboard itself |

Without the real data, set `LSA_USE_SAMPLE=1` to run on the small fake data from `make_sample_data.py`.
