# Star schema design (designed in Week 2, loaded in Week 3)

## Grain of each fact table (one sentence each)

| Fact table | One row is... | Answers KPIs |
| --- | --- | --- |
| `fact_appointments_monthly` | the count of appointments for one ICB x month x status x staff type x mode x booking wait | 1 to 8 |
| `fact_appointments_by_category` | the count of appointments for one sub-ICB location x day x service setting x national category | 9, 10, 12 |
| `fact_appointments_by_duration` | the count of appointments for one sub-ICB location x day x duration band | 11, 12 |

Each fact stores only additive counts. Rates are calculated at query time.

## Dimensions

| Dimension | Content | Used by |
| --- | --- | --- |
| `dim_geography` | 106 sub-ICB locations with ICB and region codes | category, duration (and ICB level for monthly) |
| `dim_date` | every day 2020 to 2022 with month, year, weekday | all three facts (conformed) |
| `dim_booking_wait` | wait band labels with a sort order (Same Day first) | monthly |
| `dim_duration_band` | duration band labels with a sort order | duration |
| `dim_national_category` | category with its context type | category |

## Rules
1. Never join two fact tables row by row; aggregate each to a shared level (such as month) first.
2. Store counts, not rates.
3. All facts that have a month use the same `dim_date`.
4. Bands carry a sort order so `1 Day` does not sort before `Same Day`.

## Architecture sketch

```
NHS England files (never edited)
   appointments_regional.csv   national_categories.csv   actual_duration.csv.xlsx
            |                          |                          |
            v        Week 1: extract.py  (copy, xlsx->csv, manifest.json)
        data/raw/   (not committed)
            |
            v        Week 2: transform.py  (PySpark: schema, 5 traps, Parquet by month)
        data/clean/ (not committed)        <- pytest proves totals unchanged
            |
            v        Week 3: load.py  (DuckDB star schema, delete-then-insert per month)
        warehouse/  (not committed)
            |
            v        Week 4: KPI pack + Streamlit dashboard (12 KPIs, caveats on every chart)

 run_pipeline.py runs each stage in order, logs rows and totals, stops at the first failure
```
