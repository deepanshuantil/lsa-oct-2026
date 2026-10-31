# Dashboard (Week 4)

A Streamlit dashboard with the twelve KPIs, a caveat under every chart and a panel showing the pipeline's quality checks.

| File | What it does |
|------|--------------|
| `dashboard.py` | The Streamlit app. Reads the CSV files in `data/`, calculates the rates and draws the charts. |
| `caveats.py` | Every data-quality caveat and the three Week 4 decisions, in one place. |
| `data/` | Small CSV files of aggregated counts (no personal data), made by `python src/kpis.py` from the warehouse. |
| `requirements.txt` | The few packages the hosted dashboard needs. |

Run it locally: `streamlit run app/dashboard.py`

To refresh the numbers after a new pipeline run: `python src/kpis.py`, then commit the files in `data/`.
