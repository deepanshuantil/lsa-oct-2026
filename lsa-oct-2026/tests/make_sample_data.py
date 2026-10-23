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
    rnd = random.Random(seed)
    dest.mkdir(parents=True, exist_ok=True)
    months = ["2021-10", "2021-11", "2021-12"]

    rows = []
    for icb in ICBS:
        for m in months:
            for st in STATUS:
                for hcp in STAFF:
                    for mode in MODES[:3]:
                        for w in WAITS[:4]:
                            rows.append([icb, m, st, hcp, mode, w, rnd.randint(1, 500)])
    # look-alike rows: same keys (different sub-ICBs once merged), some with identical counts (trap 4)
    rows += [list(r) for r in rows[:40]] + [r[:6] + [r[6] + 3] for r in rows[40:80]]
    pd.DataFrame(rows, columns=["icb_ons_code", "appointment_month", "appointment_status", "hcp_type",
                                "appointment_mode", "time_between_book_and_appointment",
                                "count_of_appointments"]).to_csv(dest / "appointments_regional.csv", index=False)

    locs = [(f"NHS Place {i} ICB - {c}", ICBS[i % 3]) for i, c in enumerate(["00L", "00M", "00N", "01A", "B2M3M"])]
    cat = []
    for name, icb in locs:
        for d in ["02/10/2021", "25/10/2021", "03/11/2021", "30/11/2021", "13/12/2021"]:
            mon = f"{d[6:]}-{d[3:5]}"
            for setting, ctx, c in [("General Practice", "Care Related Encounter", "Planned Clinics"),
                                    ("Primary Care Network", "Care Related Encounter", "Walk-in"),
                                    ("Unmapped", "Unmapped", "Unmapped")]:
                cat.append([d, icb, name, setting, ctx, c, rnd.randint(1, 300), mon])
    text = pd.DataFrame(cat, columns=["appointment_date", "icb_ons_code", "sub_icb_location_name", "service_setting",
                                      "context_type", "national_category", "count_of_appointments",
                                      "appointment_month"]).to_csv(index=False)
    (dest / "national_categories.csv").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))   # trap 2: BOM

    dur = []
    for i, (name, icb) in enumerate(locs):
        for d in pd.date_range("2021-12-01", periods=6):
            for band in ["1-5 Minutes", "6-10 Minutes", "Unknown / Data Quality"]:
                dur.append([f"{i:02d}X", f"E3800{i}", name, icb, "E40000003", d.to_pydatetime(), band,
                            rnd.randint(1, 200)])
    pd.DataFrame(dur, columns=["sub_icb_location_code", "sub_icb_location_ons_code", "sub_icb_location_name",
                               "icb_ons_code", "region_ons_code", "appointment_date", "actual_duration",
                               "count_of_appointments"]).to_excel(dest / "actual_duration.csv.xlsx", index=False)  # trap 1
    return dest


if __name__ == "__main__":
    print("sample data written to", build(Path(sys.argv[1] if len(sys.argv) > 1 else "data/sample_raw")))
