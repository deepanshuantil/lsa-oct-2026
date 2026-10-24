"""Builds a SMALL fake raw folder with the same five traps as the real files, so the
tests and pipeline can run anywhere (laptop, GitHub Actions) without the NHS data.

    python tests/make_sample_data.py data/sample_raw
"""
import random
import sys
from pathlib import Path

import pandas as pd

WAITS = ["Same Day", "1 Day", "2 to 7 Days", "8  to 14 Days", "15  to 21 Days", "22  to 28 Days",
         "More than 28 Days", "Unknown / Data Quality"]          # note the double spaces (trap 5)
STAFF = ["GP", "Other Practice staff", "Unknown"]                  # lower-case 's' (trap 5)
STATUS = ["Attended", "DNA", "Unknown"]
MODES = ["Face-to-Face", "Home Visit", "Telephone", "Unknown", "Video/Online"]
ICBS = ["E54000001", "E54000002", "E54000003"]


def build(dest: Path, seed: int = 7) -> Path:
    """Fake raw folder whose three files RECONCILE like the real ones: the regional monthly
    totals equal the category monthly totals, and the duration file holds about 92% of them,
    with the same sub-ICB codes as the category file."""
    rnd = random.Random(seed)
    dest.mkdir(parents=True, exist_ok=True)
    days = ["02/10/2021", "25/10/2021", "03/11/2021", "30/11/2021", "13/12/2021"]
    locs = [(f"NHS Place {i} ICB - {c}", c, ICBS[i % 3]) for i, c in enumerate(["00L", "00M", "00N", "01A", "B2M3M"])]

    # --- categories (first, so the other two can be built to match it)
    cat, day_loc_total, month_icb_total = [], {}, {}
    for name, code, icb in locs:
        for d in days:
            mon = f"{d[6:]}-{d[3:5]}"
            for setting, ctx, c in [("General Practice", "Care Related Encounter", "Planned Clinics"),
                                    ("Primary Care Network", "Care Related Encounter", "Walk-in"),
                                    ("Unmapped", "Unmapped", "Unmapped")]:
                n = rnd.randint(20, 300)
                cat.append([d, icb, name, setting, ctx, c, n, mon])
                day_loc_total[(d, code)] = day_loc_total.get((d, code), 0) + n
                month_icb_total[(icb, mon)] = month_icb_total.get((icb, mon), 0) + n
    text = pd.DataFrame(cat, columns=["appointment_date", "icb_ons_code", "sub_icb_location_name", "service_setting",
                                      "context_type", "national_category", "count_of_appointments",
                                      "appointment_month"]).to_csv(index=False)
    (dest / "national_categories.csv").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))   # trap 2: BOM

    # --- regional: split each (icb, month) total over many keys, then split some rows in two
    # look-alikes (trap 4) whose counts add back to the original, so summing them is required.
    rows = []
    for (icb, mon), total in sorted(month_icb_total.items()):
        keys = [(st, hcp, mode, w) for st in STATUS for hcp in STAFF for mode in MODES[:3] for w in WAITS[:4]]
        weights = [rnd.randint(1, 9) for _ in keys]
        counts = [total * w // sum(weights) for w in weights]
        counts[0] += total - sum(counts)
        for (st, hcp, mode, w), c in zip(keys, counts):
            if c >= 2 and rnd.random() < 0.3:
                a = rnd.randint(1, c - 1)
                rows += [[icb, mon, st, hcp, mode, w, a], [icb, mon, st, hcp, mode, w, c - a]]
            else:
                rows.append([icb, mon, st, hcp, mode, w, c])
    pd.DataFrame(rows, columns=["icb_ons_code", "appointment_month", "appointment_status", "hcp_type",
                                "appointment_mode", "time_between_book_and_appointment",
                                "count_of_appointments"]).to_csv(dest / "appointments_regional.csv", index=False)

    # --- duration: about 92% of each day/location total, same codes, bands add up
    dur = []
    for i, (name, code, icb) in enumerate(locs):
        for d in [x for x in days if x[3:5] != "10"]:
            target = int(day_loc_total[(d, code)] * 0.92)
            a = target // 3
            b = target // 3
            parts = [a, b, target - a - b]
            day = pd.to_datetime(d, format="%d/%m/%Y").to_pydatetime()
            for band, n in zip(["1-5 Minutes", "6-10 Minutes", "Unknown / Data Quality"], parts):
                dur.append([code, f"E3800{i}", name, icb, "E40000003", day, band, n])
    pd.DataFrame(dur, columns=["sub_icb_location_code", "sub_icb_location_ons_code", "sub_icb_location_name",
                               "icb_ons_code", "region_ons_code", "appointment_date", "actual_duration",
                               "count_of_appointments"]).to_excel(dest / "actual_duration.csv.xlsx", index=False)  # trap 1
    return dest


if __name__ == "__main__":
    print("sample data written to", build(Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample_raw")))
