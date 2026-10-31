# Data profile

Generated 2026-10-13 19:04 UTC by `src/profile.py` from `/content/drive/MyDrive/LSA\_Oct2026/data\_raw/`.

Source: NHS England, Appointments in General Practice.

## appointments\_regional.csv

**Grain (what one row is):** Appointments for one ICB, month, status, staff type, mode and booking wait

**Rows:** 596,821  |  **Columns:** 7

|Column|Type|Nulls|Distinct|Min|Max|
|-|-|-|-|-|-|
|`icb\_ons\_code`|text|0 (0.0%)|42|||
|`appointment\_month`|date|0 (0.0%)|30|2020-01-01|2022-06-01|
|`appointment\_status`|text|0 (0.0%)|3|||
|`hcp\_type`|text|0 (0.0%)|3|||
|`appointment\_mode`|text|0 (0.0%)|5|||
|`time\_between\_book\_and\_appointment`|text|0 (0.0%)|8|||
|`count\_of\_appointments`|integer|0 (0.0%)|22,807|1|211,265|

**Distinct values of low-cardinality text columns** (look for messy labels):

* `appointment\_status` (3): `Attended` (232,137); `DNA` (163,360); `Unknown` (201,324)
* `hcp\_type` (3): `GP` (226,036); `Other Practice staff` (241,557); `Unknown` (129,228)
* `appointment\_mode` (5): `Face-to-Face` (180,410); `Home Visit` (111,194); `Telephone` (166,483); `Unknown` (79,147); `Video/Online` (59,587)
* `time\_between\_book\_and\_appointment` (8): `1 Day` (88,957); `15  to 21 Days` (73,666); `2 to 7 Days` (92,409); `22  to 28 Days` (68,755); `8  to 14 Days` (82,698); `More than 28 Days` (65,147); `Same Day` (95,502); `Unknown / Data Quality` (29,687)

## national\_categories.csv

**Grain (what one row is):** Appointments for one sub-ICB location, day, service setting and national category

**Rows:** 817,394  |  **Columns:** 8

|Column|Type|Nulls|Distinct|Min|Max|
|-|-|-|-|-|-|
|`appointment\_date`|date|0 (0.0%)|334|2021-08-01|2022-06-30|
|`icb\_ons\_code`|text|0 (0.0%)|42|||
|`sub\_icb\_location\_name`|text|0 (0.0%)|106|||
|`service\_setting`|text|0 (0.0%)|5|||
|`context\_type`|text|0 (0.0%)|3|||
|`national\_category`|text|0 (0.0%)|18|||
|`count\_of\_appointments`|integer|0 (0.0%)|9,957|1|16,590|
|`appointment\_month`|date|0 (0.0%)|11|2021-08-01|2022-06-01|

**Distinct values of low-cardinality text columns** (look for messy labels):

* `service\_setting` (5): `Extended Access Provision` (108,122); `General Practice` (359,274); `Other` (138,789); `Primary Care Network` (183,790); `Unmapped` (27,419)
* `context\_type` (3): `Care Related Encounter` (700,481); `Inconsistent Mapping` (89,494); `Unmapped` (27,419)
* `national\_category` (18): `Care Home Needs Assessment \& Personalised Care and Support Planning` (23,505); `Care Home Visit` (26,644); `Clinical Triage` (74,539); `General Consultation Acute` (84,874); `General Consultation Routine` (89,329); `Group Consultation and Group Education` (5,341); `Home Visit` (41,850); `Inconsistent Mapping` (89,494); `Non-contractual chargeable work` (20,896); `Patient contact during Care Home Round` (28,795); `Planned Clinical Procedure` (59,631); `Planned Clinics` (76,429); `Service provided by organisation external to the practice` (43,095); `Social Prescribing Service` (26,492); `Structured Medication Review` (44,467); `Unmapped` (27,419); `Unplanned Clinical Activity` (40,415); `Walk-in` (14,179)

## actual\_duration.csv

**Grain (what one row is):** Appointments for one sub-ICB location, day and consultation-length band

**Rows:** 137,793  |  **Columns:** 8

|Column|Type|Nulls|Distinct|Min|Max|
|-|-|-|-|-|-|
|`sub\_icb\_location\_code`|text|0 (0.0%)|106|||
|`sub\_icb\_location\_ons\_code`|text|0 (0.0%)|106|||
|`sub\_icb\_location\_name`|text|0 (0.0%)|106|||
|`icb\_ons\_code`|text|0 (0.0%)|42|||
|`region\_ons\_code`|text|0 (0.0%)|7|||
|`appointment\_date`|date|0 (0.0%)|212|2021-12-01|2022-06-30|
|`actual\_duration`|text|0 (0.0%)|7|||
|`count\_of\_appointments`|integer|0 (0.0%)|7,611|1|15,400|

**Distinct values of low-cardinality text columns** (look for messy labels):

* `region\_ons\_code` (7): `E40000003` (7,120); `E40000005` (15,130); `E40000006` (9,465); `E40000007` (18,888); `E40000010` (33,112); `E40000011` (25,015); `E40000012` (29,063)
* `actual\_duration` (7): `1-5 Minutes` (19,909); `11-15 Minutes` (19,738); `16-20 Minutes` (19,534); `21-30 Minutes` (19,452); `31-60 Minutes` (19,097); `6-10 Minutes` (19,902); `Unknown / Data Quality` (20,161)

# The five traps

# Total appointments (evidence that nothing was lost)

These totals come from summing `count_of_appointments` in each raw file. Every later stage must reproduce them exactly.

- appointments_regional.csv: 742,804,525
- national_categories.csv: 296,046,770
- actual_duration.csv: 167,980,692

## 1\. `actual\_duration.csv.xlsx` is an Excel file, not a CSV

First bytes of the file: `b'PK\\x03\\x04'`. `PK` means a zip container, which is how .xlsx files are stored: **confirmed Excel**. Fix: converted to CSV with pandas in `extract.py`.

## 2\. Hidden byte-order mark in `national\_categories.csv`

First three bytes: `b'\\xef\\xbb\\xbf'`; first column read as `'\\ufeffappointment\_date'`. `EF BB BF` is the UTF-8 BOM: **confirmed**. Fix: strip `\\ufeff` from column names in Week 2.

## 3\. Day-first dates in `national\_categories.csv`

Column `appointment\_date`: first part ranges 1-31, second part 1-12. The first part goes above 12 while the second never does, so the format is **dd/MM/yyyy**. Always state it explicitly: `to\_date(col, 'dd/MM/yyyy')`.

## 4\. Exact duplicate rows in `appointments\_regional.csv`

Rows that exactly repeat an earlier row: **21,604** (plan says 21,604). Rows involved in any duplicate group: 40,135.

These are **real data, not errors**: the sub-ICB columns were removed, so different sub-ICBs in the same ICB produce identical rows. **Aggregate (sum) them; never drop them.**

## 5\. Messy labels

* `appointments\_regional.csv` / `time\_between\_book\_and\_appointment`: double spaces in \['8  to 14 Days', '15  to 21 Days', '22  to 28 Days']

**Also check by hand:** compare the staff-type labels with `metadata\_nhs.txt` (the plan notes *Other Practice staff* vs *Other Practice Staff*), and note that alphabetical order puts `1 Day` before `Same Day`, so the wait bands need an explicit sort order.

# Notes

## Which trap surprised me most
The 21,604 duplicate rows in the regional file surprised me most. Normally I would drop exact duplicates, but here they are real appointments. The sub-ICB columns were removed from this file, so two sub-ICBs in the same ICB can produce identical rows. The correct fix is to sum them, not delete them.

## What would have gone wrong silently without profiling
Several problems would have failed silently. Dropping the duplicates would have deleted real appointments, so the regional total would not match the categories file. Spark cannot read `actual_duration.csv.xlsx` because it is an Excel file, not a CSV. The hidden byte-order mark would have turned the first column into `\ufeffappointment_date`, so queries for `appointment_date` would fail. Reading the day-first dates without stating the format would have turned 2 August 2021 into the wrong date or left the column as text. None of these would have shown an obvious error, only wrong numbers.

## A data-quality caveat from the metadata
Between 3% and 10% of appointments each month are recorded with Unknown status (highest in March and April 2020, about 4% in 2022), because the appointment stayed "Booked" and nobody knows whether it took place. Any attendance or DNA rate is therefore based on incomplete data, and the dashboard says so.
