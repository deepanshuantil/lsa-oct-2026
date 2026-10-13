"""
Data profile: reads the raw files and writes docs/data_profile.md.

For each file: grain, columns and types, nulls, distinct values, date range.
Then it checks for the five known traps and writes down what it found.

Usage (from the repo root):
    python src/profile.py --raw data/raw --out docs/data_profile.md
"""
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

FILES = {
    "appointments_regional.csv": "Appointments for one ICB, month, status, staff type, mode and booking wait",
    "national_categories.csv": "Appointments for one sub-ICB location, day, service setting and national category",
    "actual_duration.csv": "Appointments for one sub-ICB location, day and consultation-length band",
}

DATE_PATTERNS = [r"^\d{2}/\d{2}/\d{4}$", r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}:\d{2})?$",
                 r"^\d{4}-\d{2}$", r"^[A-Za-z]{3,9}[- ]?\d{2,4}$"]
DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m", "%b-%y", "%b%Y",
                "%b %Y", "%b-%Y", "%B %Y", "%b%y"]


def load(path: Path) -> pd.DataFrame:
    # Everything as text: nothing guessed, blanks stay blank. utf-8-sig only
    # affects reading; to see the BOM we also inspect the raw bytes separately.
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def blank_mask(s: pd.Series) -> pd.Series:
    return s.str.strip() == ""


def infer_type(vals: pd.Series) -> str:
    if vals.empty:
        return "empty"
    if vals.str.fullmatch(r"-?\d+").all():
        return "integer"
    if pd.to_numeric(vals, errors="coerce").notna().all():
        return "decimal"
    sample = vals.head(2000)
    if any(sample.str.fullmatch(p).mean() >= 0.95 for p in DATE_PATTERNS):
        return "date"
    return "text"


def parse_dates(vals: pd.Series):
    best, best_n = None, -1
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(vals, format=fmt, errors="coerce")
        if parsed.notna().sum() > best_n:
            best, best_n = parsed, parsed.notna().sum()
    return best


def profile_file(name: str, df: pd.DataFrame, out: list) -> dict:
    out.append(f"## {name}\n")
    out.append(f"**Grain (what one row is):** {FILES[name]}\n")
    out.append(f"**Rows:** {len(df):,}  |  **Columns:** {len(df.columns)}\n")
    out.append("| Column | Type | Nulls | Distinct | Min | Max |")
    out.append("| --- | --- | --- | --- | --- | --- |")
    types = {}
    lowcard = {}
    for col in df.columns:
        s = df[col]
        nulls = int(blank_mask(s).sum())
        vals = s[~blank_mask(s)]
        t = infer_type(vals)
        types[col] = t
        distinct = vals.nunique()
        lo = hi = ""
        if t == "date":
            d = parse_dates(vals).dropna()
            if len(d):
                lo, hi = d.min().date().isoformat(), d.max().date().isoformat()
        elif t in ("integer", "decimal"):
            n = pd.to_numeric(vals)
            lo, hi = f"{n.min():,}", f"{n.max():,}"
        if t == "text" and 0 < distinct <= 30:
            lowcard[col] = vals.value_counts(dropna=False)
        out.append(f"| `{col}` | {t} | {nulls:,} ({nulls/len(df):.1%}) | {distinct:,} | {lo} | {hi} |")
    out.append("")
    if lowcard:
        out.append("**Distinct values of low-cardinality text columns** (look for messy labels):\n")
        for col, vc in lowcard.items():
            items = "; ".join(f"`{k}` ({v:,})" for k, v in vc.sort_index().items())
            out.append(f"- `{col}` ({len(vc)}): {items}")
        out.append("")
    return {"types": types, "lowcard": lowcard}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="docs/data_profile.md")
    args = ap.parse_args()
    raw = Path(args.raw)

    out = ["# Data profile\n",
           f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `src/profile.py` from `{raw}/`.\n",
           "Source: NHS England, Appointments in General Practice.\n"]
    dfs, info = {}, {}
    for name in FILES:
        dfs[name] = load(raw / name)
        info[name] = profile_file(name, dfs[name], out)

    reg, cat, dur = (dfs[n] for n in FILES)
    out.append("# The five traps\n")

    # 1. Fake CSV
    xl = raw / "actual_duration.csv.xlsx"
    head = xl.read_bytes()[:4] if xl.exists() else b""
    out.append("## 1. `actual_duration.csv.xlsx` is an Excel file, not a CSV\n")
    out.append(f"First bytes of the file: `{head!r}`. "
               + ("`PK` means a zip container, which is how .xlsx files are stored: **confirmed Excel**. "
                  "Fix: converted to CSV with pandas in `extract.py`.\n" if head[:2] == b"PK"
                  else "Not found / not Excel; check the file.\n"))

    # 2. BOM
    cp = raw / "national_categories.csv"
    first3 = cp.read_bytes()[:3]
    first_col = open(cp, encoding="utf-8", newline="").readline().split(",")[0]
    out.append("## 2. Hidden byte-order mark in `national_categories.csv`\n")
    out.append(f"First three bytes: `{first3!r}`; first column read as `{first_col!r}`. "
               + ("`EF BB BF` is the UTF-8 BOM: **confirmed**. Fix: strip `\\ufeff` from column names in Week 2.\n"
                  if first3 == b"\xef\xbb\xbf" else "No BOM found.\n"))

    # 3. Day-first dates
    out.append("## 3. Day-first dates in `national_categories.csv`\n")
    found = False
    for col, t in info["national_categories.csv"]["types"].items():
        v = cat[col]
        v = v[v.str.fullmatch(r"\d{2}/\d{2}/\d{4}")]
        if len(v) and t == "date":
            found = True
            a, b = v.str[:2].astype(int), v.str[3:5].astype(int)
            out.append(f"Column `{col}`: first part ranges {a.min()}-{a.max()}, second part {b.min()}-{b.max()}. "
                       + ("The first part goes above 12 while the second never does, so the format is **dd/MM/yyyy**. "
                          "Always state it explicitly: `to_date(col, 'dd/MM/yyyy')`.\n" if a.max() > 12 >= b.max()
                          else "Could not prove the order from the values; check the metadata.\n"))
    if not found:
        out.append("No dd/mm/yyyy-style column detected; check the profile table above.\n")

    # 4. Duplicates
    dup_keep_first = int(reg.duplicated().sum())
    dup_all = int(reg.duplicated(keep=False).sum())
    out.append("## 4. Exact duplicate rows in `appointments_regional.csv`\n")
    out.append(f"Rows that exactly repeat an earlier row: **{dup_keep_first:,}** (plan says 21,604). "
               f"Rows involved in any duplicate group: {dup_all:,}.\n")
    out.append("These are **real data, not errors**: the sub-ICB columns were removed, so different sub-ICBs in the same "
               "ICB produce identical rows. **Aggregate (sum) them; never drop them.**\n")

    # 5. Messy labels
    out.append("## 5. Messy labels\n")
    issues = 0
    for name, d in dfs.items():
        for col, vc in info[name]["lowcard"].items():
            labels = list(vc.index)
            dbl = [x for x in labels if re.search(r"\s{2,}", x)]
            edge = [x for x in labels if x != x.strip()]
            groups = {}
            for x in labels:
                groups.setdefault(re.sub(r"\s+", " ", x.strip()).casefold(), []).append(x)
            variants = [g for g in groups.values() if len(g) > 1]
            if dbl:
                issues += 1
                out.append(f"- `{name}` / `{col}`: double spaces in {dbl}")
            if edge:
                issues += 1
                out.append(f"- `{name}` / `{col}`: leading/trailing spaces in {edge}")
            if variants:
                issues += 1
                out.append(f"- `{name}` / `{col}`: same label spelled differently {variants}")
    out.append("")
    out.append("**Also check by hand:** compare the staff-type labels with `metadata_nhs.txt` "
               "(the plan notes *Other Practice staff* vs *Other Practice Staff*), and note that "
               "alphabetical order puts `1 Day` before `Same Day`, so the wait bands need an explicit sort order.\n")

    out.append("# My notes\n")
    out.append("_Write 3 to 5 sentences here in your own words: which trap surprised you most, what would have gone "
               "wrong silently if you had not profiled first, and one data-quality caveat from section 4 of the metadata._\n")

    Path(args.out).parent.mkdir(parents=True,
