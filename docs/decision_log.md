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
| 13 | Every date column is parsed with one stated format (`yyyy-MM` for both `appointment_month` columns, `yyyy-MM-dd HH:mm:ss` for the duration `appointment_date`), found by counting the text pattern of every row in each raw column | The earlier code tried eight formats and took the first that fit, which is guessing. A wrong guess changes the month without any error | 596,821 / 817,394 / 137,793 |

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
Each rule was broken on purpose to prove its test can fail.

**On the real NHS data**

| Rule broken | Test that failed |
| --- | --- |
| Staff spelling not unified (`Other Practice staff` left as it was) | `test_one_spelling_of_other_practice_staff` |

**On the sample data** (small fake files with the same five traps)

| Rule broken | What failed |
| --- | --- |
| `dropDuplicates` instead of summing | the stage's own total check, and `test_totals_preserved` |
| tidy step removed | `test_no_double_or_edge_spaces_in_any_text_column` |
| date parsed month-first | `test_parse_day_first_unit` |
| bad sub-ICB regex | the stage's own check, and `test_sub_icb_code_taken_from_end_of_name` |
| partitioning removed | `test_parquet_is_partitioned_by_month` |
| `appointment_month` format loosened to `yyyy-MM-dd` | the pipeline stopped with an error at the first stage |

## H. Final results on the real data
- Regional: 596,821 rows to 295,692, total 742,804,525
- Categories: total 296,046,770
- Duration: total 167,980,692
- A second run gave identical results
- Tests (Week 2): 26 passed, none skipped (Week 3 raised this to 46, see section I)

## I. Week 3: load and automate

| # | Decision | Why |
|---|----------|-----|
| 14 | Three fact tables, not one | The files have different grains (month x ICB, day x sub-ICB x category, day x sub-ICB x duration). Merging them would double count or invent rows. |
| 15 | Facts hold counts only; descriptions live in dimensions | Facts stay small and a label is fixed in one place. |
| 16 | Load = delete the month, insert the month, inside one transaction | Running the load twice gives the same result, and a failure part way leaves the old month untouched (both tested). |
| 17 | The load does no grouping and no de-duplication | The look-alike regional rows were summed in the transform. Doing it again would delete real appointments. |
| 18 | Load into warehouse.duckdb.staging, run the checks, then swap in | A failed check must not leave a half-wrong warehouse. Exit code 2 means nothing was written. |
| 19 | Expected totals are literal numbers in config.py | A check that recomputes its expectation from the data it checks can never fail. |
| 20 | Reconcile regional against categories only for Aug 2021 to Jun 2022 | The two files only overlap in that window. |
| 21 | Duration coverage is a range (90% to 100%) over the months both files share | The duration file starts later than categories (Dec 2021 to Jun 2022, 7 months against 11) because the NHS first published actual duration in the April 2022 release (metadata_nhs.txt section 4). It holds 90.9% to 92.2% of the categories total each month because duration only exists for consultations that took place (section 4: the length of the consultation that took place), so DNA and unresolved 'Booked' appointments have none. Verified on the real data: for every one of the 7 months, duration divided by categories equals the Attended share of the regional file to four decimal places (for example 0.9090 in Dec 2021 and 0.9182 in Jun 2022). My first version compared all 11 months of categories and wrongly failed at 56.7%. |
| 22 | dim_geography comes from the duration file; facts that only know the ICB use the view v_icb | dim_geography has many rows per ICB, so joining a fact to it would multiply rows. |
| 23 | Band labels have an explicit sort_order and an is_known flag | Alphabetical order puts "1 Day" before "Same Day", and "Unknown / Data Quality" must be excluded from rates. |

Results: all 9 checks pass, totals match the profile exactly, 46 tests pass.

## J. Week 4: dashboard

| # | Decision | Reason |
|---|----------|--------|
| 24 | Every rate leaves Unknown out of the denominator (status, mode, staff type, booking wait, duration) | Unknown means we do not know the answer. Counting it as "not DNA" or "not face-to-face" would invent a result. About 3% to 6% of appointments have Unknown status each month. |
| 25 | Year-on-year compares a month with the same month a year earlier, never a full year with a half year | The regional file ends in June 2022, so 2022 has six months. A month with no prior year shows blank, not 0, because 0 would give a false -100% change. |
| 26 | No per-1,000-patients figures and no raw totals compared between ICBs | The files have no registered-patient count. ICBs are compared by rates only, and the caveat says small ICBs can look extreme. |
| 27 | The dashboard reads small CSV files of counts (app/data), not the warehouse | warehouse.duckdb is git-ignored (too big and not for GitHub), so a hosted app cannot see it. The CSVs hold aggregated counts only, nothing personal. Rates are computed in the dashboard from the counts, as in decision 15. |
| 28 | All caveat wording lives in app/caveats.py | One place to edit, and every chart shows the caveat that affects it. |

