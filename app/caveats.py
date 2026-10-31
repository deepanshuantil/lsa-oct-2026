"""Every data-quality caveat in ONE place.

The Week 3 guidance says: keep the caveats in one file, because every chart needs the caveat that
affects it and you will not want to hunt for them on presentation day. dashboard.py reads this file
and shows the right caveat under each chart. Edit the wording here and every chart updates.
"""

CAVEATS = {
    "demand": (
        "Regional file, January 2020 to June 2022. 2022 has only six months, so compare month with month "
        "(or January to June with January to June), never a full year with a half year. The files hold no "
        "patient population, so you cannot work out appointments per 1,000 patients and raw totals should "
        "not be compared between areas of different size."
    ),
    "wait": (
        "Rates use only appointments with a KNOWN booking wait. Appointments labelled "
        "'Unknown / Data Quality' are left out of the denominator. 'Long wait' means booked more than "
        "14 days ahead (15 to 21 days, 22 to 28 days, more than 28 days)."
    ),
    "dna": (
        "DNA rate = DNA / (Attended + DNA). Appointments with Unknown status are left out: between 3% and 6% "
        "of appointments each month stay 'Booked' and nobody knows whether they took place, so every "
        "attendance rate is based on incomplete data. The NHS notes also mention an early data-collection "
        "issue with DNA counts (see metadata_nhs.txt, section 2)."
    ),
    "icb": (
        "ICBs are shown by code only; the files hold no names. Rates are used, not raw counts, because the files "
        "hold no population figures. Small ICBs can look extreme because their numbers are small."
    ),
    "mode": (
        "Appointment mode is set locally by each practice and may be recorded inconsistently. Shares leave out "
        "Unknown mode (face-to-face) and Unknown staff type (GP share)."
    ),
    "weekday": (
        "Categories file only: August 2021 to June 2022. Each day is added up first, then the days are averaged by "
        "day of the week. Bank holidays pull the average down."
    ),
    "network": (
        "Categories file only: August 2021 to June 2022. Counts Primary Care Network and Extended Access "
        "Provision appointments as a share of all appointments in that file."
    ),
    "duration": (
        "Duration file only: December 2021 to June 2022 (the NHS first published actual duration in April 2022). "
        "It covers only consultations that took place, about 92% of the categories file. Duration is recorded "
        "differently by each GP system supplier. Share = 16 to 60 minute bands / appointments with a known duration."
    ),
    "quality": (
        "These two measures show how much of each file is labelled 'Unmapped', 'Inconsistent Mapping' or "
        "'Unknown / Data Quality'. A higher share means the matching charts deserve less trust."
    ),
}

DECISIONS = [
    ("Denominators", "Every rate excludes 'Unknown' (status, mode, staff type, booking wait, duration) from the "
                     "denominator. Including Unknown would give a different, lower rate."),
    ("Partial years", "The regional file ends in June 2022. Year-on-year change compares a month with the same "
                      "month a year earlier, never a full year with a half year."),
    ("Missing population", "There is no registered-patient count in these files, so there are no appointments "
                           "per 1,000 patients. Do not compare raw totals between ICBs of different sizes."),
]
