# Decision log

One line per decision: what changed, why, and how many rows it affected.
Row counts come from `data_profile.md` (Week 1) and the brief; fill the "run" column from your own `logs/pipeline.log`.

## A. Data cleaning (the five traps)

| # | Decision | Why | Rows affected |
| --- | --- | --- | --- |
| 1 | Read `actual_duration.csv.xlsx` with pandas and write `actual_duration.csv` (in `extract.py`), all values as text | The file is Excel despite its name; Spark cannot read it. Text keeps codes like `00L` intact | 137,793 |
| 2 | Strip `﻿` from the header of `national_categories.csv` and check the header against the declared schema | A hidden byte-order mark would rename the first column | 1 header (817,394 data rows read safely) |
| 3 | Parse `appointment_date` with `to_date(col, "dd/MM/yyyy")` into a new column `appointment_day` | Dates are day-first (first part reaches 31, second never above 12). Month-first would put appointments in the wrong month | 817,394 |
| 4 | Group the regional file by every descriptive column and **sum** the counts; never drop rows | The sub-ICB columns were removed, so different sub-ICBs in one ICB produce the same key (21,604 exact copies, plus rows with the same key and a different count). Dropping would delete real appointments | 596,821 -> 295,692 (301,129 merged); total unchanged at 742,804,525 |
| 5a | Collapse repeated spaces and trim every text column | `8  to 14 Days`, `15  to 21 Days`, `22  to 28 Days` contain double spaces | 225,119 regional rows |
| 5b | Use one spelling, `Other Practice Staff` | The file says `Other Practice staff`; the metadata says `Other Practice Staff` | 241,557 regional rows |

## B. Design decisions

| # | Decision | Why | Rows affected |
| --- | --- | --- | --- |
| 6 | Explicit schemas (`StructType`), `FAILFAST` reads, no `inferSchema` | A guessed type can change silently when a new file arrives | all |
| 7 | Counts stay whole numbers (`bigint`); no rates in the clean layer | Rates cannot be added or averaged; compute them at query time | all |
| 8 | New columns (`month_start`, `appointment_day`, `sub_icb_code`) sit beside the original columns | Anyone can compare clean against raw | all |
| 9 | `sub_icb_code` taken from the end of `sub_icb_location_name` (`... ICB - 00L` -> `00L`) | The categories file has no code column | 817,394 |
| 10 | Parquet partitioned by `month_start` | Queries read only the months they need; DuckDB reads the folders directly in Week 3 | 30 / 11 / 7 months |
| 11 | Every stage writes with `mode("overwrite")` | Rerunning gives the same output, never doubles | all |
| 12 | Totals checked before and after tidy, after summing, and against the brief | Proves nothing was lost or invented | all |

## C. Denominators (each one changes the answer)

State the choice beside every rate. These are the defaults used in Week 4; change one only if you can justify it here.

| KPI | Denominator choice |
| --- | --- |
| 3 Same-day share | Appointments with a **known** wait (excludes `Unknown / Data Quality`) |
| 4 Long-wait share | Appointments with a known wait; "long" means booked more than 14 days ahead (`15 to 21`, `22 to 28`, `More than 28 Days`) |
| 5, 6 DNA rate | Attended + DNA, **excluding Unknown status** (3 to 6% of appointments stay Unknown, so the rate is an estimate) |
| 7 Face-to-face share | Appointments with a known mode |
| 8 GP share | Appointments with a known staff type (only "GP" is recorded consistently) |
| 11 Share longer than 15 minutes | Appointments with a known duration (excludes `Unknown / Data Quality`) |

## D. Partial years
The regional file ends in June 2022, so 2022 has six months. KPI 2 compares the same month with the same month a year earlier; any yearly comparison uses January to June against January to June, never a full year against a half.

## E. Missing population
No registered-patient count exists in these files, so appointments per 1,000 patients cannot be calculated. The dashboard says so instead of comparing raw totals between ICBs of different sizes.

## F. Why three fact tables, not one flat table
The files have three different grains (ICB x month x status..., sub-ICB x day x category, sub-ICB x day x duration band). One flat table would mix those grains, repeat geography names on every row, and give wrong totals whenever someone filters across files. Joining the facts row by row would multiply rows and inflate totals, so they are compared only after aggregating each to a shared level such as month. The Week 3 reconciliation (regional total = category total for every month from August 2021 to June 2022) does exactly that.

## G. Tests proven able to fail
Each rule was broken on purpose and the test suite went red (run on the sample data):

| Rule broken | What failed |
| --- | --- |
| `dropDuplicates` instead of summing | stage's own total check (and `test_totals_preserved`) |
| tidy step removed | `test_no_double_or_edge_spaces_in_any_text_column` |
| staff spelling not unified | `test_one_spelling_of_other_practice_staff` |
| date parsed month-first | `test_parse_day_first_unit` |
| bad sub-ICB regex | stage's own check (and `test_sub_icb_code_taken_from_end_of_name`) |
| partitioning removed | `test_parquet_is_partitioned_by_month` |

Repeat this on the real data and record what you see.
