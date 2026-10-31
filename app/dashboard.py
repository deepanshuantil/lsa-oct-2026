"""GP appointments dashboard (Week 4).

Run it:   streamlit run app/dashboard.py

How it works, in plain words:
  1. src/kpis.py asks the warehouse 8 questions and saves the answers as small CSV files in app/data/.
     Those files hold COUNTS only.
  2. This file reads the CSVs, works out the rates (DNA rate, shares...) and draws the charts.
  3. Streamlit turns every `st.something(...)` line into a piece of the web page, top to bottom.
Every chart has its caveat underneath (the wording lives in caveats.py).
"""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from caveats import CAVEATS, DECISIONS

# Where the CSV files are. KPI_DIR can be set to point somewhere else (used by the tests).
DATA_DIR = Path(os.environ.get("KPI_DIR", Path(__file__).parent / "data"))

# One colour palette for every chart so the dashboard looks like one piece.
BLUE, ORANGE, RED = "#0B7A8F", "#E09F3E", "#A1263B"

st.set_page_config(page_title="GP appointments", layout="wide")


# ----------------------------------------------------------------- loading
@st.cache_data
def load(name: str) -> pd.DataFrame:
    """Read one CSV. cache_data means Streamlit remembers it instead of re-reading on every click."""
    path = DATA_DIR / f"{name}.csv"
    df = pd.read_csv(path)
    if "month_start" in df.columns:
        df["month_start"] = pd.to_datetime(df["month_start"])
    return df


def pct(numerator, denominator):
    """A percentage, or NaN (blank) when we cannot divide by zero."""
    return (numerator / denominator.where(denominator > 0)) * 100


def in_range(df: pd.DataFrame, start, end) -> pd.DataFrame:
    return df[(df["month_start"] >= start) & (df["month_start"] <= end)]


def line(df, y, title, ytitle="%", colors=None):
    """A line chart with months across the bottom."""
    fig = px.line(df, x="month_start", y=y, markers=True, title=title,
                  color_discrete_sequence=colors or [BLUE, ORANGE])
    fig.update_layout(xaxis_title="", yaxis_title=ytitle, legend_title="", margin=dict(t=60, b=20))
    return fig


def show(fig, caveat_key: str):
    """Draw the chart, then its caveat directly underneath."""
    st.plotly_chart(fig, width="stretch")
    st.caption("Caveat: " + CAVEATS[caveat_key])


# ----------------------------------------------------------------- check the data exists
if not (DATA_DIR / "monthly_totals.csv").exists():
    st.error(f"No dashboard data found in {DATA_DIR}. Run `python run_pipeline.py` and then "
             "`python src/kpis.py` to create it.")
    st.stop()

totals = load("monthly_totals")
all_months = list(totals["month_start"].sort_values())

# ----------------------------------------------------------------- sidebar: choose the months
st.sidebar.header("Choose months")
first, last = st.sidebar.select_slider(
    "Month range", options=all_months, value=(all_months[0], all_months[-1]),
    format_func=lambda d: d.strftime("%b %Y"))
st.sidebar.caption("Applies to the monthly charts. Some files cover fewer months (see each caveat).")

st.title("GP appointments in England")
st.write("Twelve measures answering the Director of Primary Care's five questions. "
         "Source: NHS England, Appointments in General Practice. A training project, not an official NHS product.")

# ----------------------------------------------------------------- the numbers used by several tabs
t = in_range(totals, first, last).copy()
t["yoy_pct"] = (t["appointments"] - t["appointments_last_year"]) / t["appointments_last_year"] * 100

dna = in_range(load("dna_monthly"), first, last).copy()
dna["dna_rate"] = pct(dna["dna"], dna["attended"] + dna["dna"])

wait = in_range(load("wait_monthly"), first, last).copy()
wait["Same-day share"] = pct(wait["same_day"], wait["known_wait"])
wait["Long-wait share (over 14 days)"] = pct(wait["long_wait"], wait["known_wait"])

mix = in_range(load("mix_monthly"), first, last).copy()
mix["Face-to-face share"] = pct(mix["face_to_face"], mix["known_mode"])
mix["GP share"] = pct(mix["gp"], mix["known_staff"])

# ----------------------------------------------------------------- headline numbers
latest = t.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Appointments, {latest['month_start']:%b %Y}", f"{int(latest['appointments']):,}",
          None if pd.isna(latest["yoy_pct"]) else f"{latest['yoy_pct']:+.1f}% on a year earlier")
if len(dna):
    c2.metric("DNA rate (latest month)", f"{dna.iloc[-1]['dna_rate']:.1f}%")
if len(wait):
    c3.metric("Same-day share", f"{wait.iloc[-1]['Same-day share']:.1f}%")
if len(mix):
    c4.metric("Face-to-face share", f"{mix.iloc[-1]['Face-to-face share']:.1f}%")

tabs = st.tabs(["Is demand rising?", "Seen quickly?", "Missed appointments", "How care is delivered",
                "Consultation length", "Can we trust the numbers?"])

# ----------------------------------------------------------------- KPI 1 and 2
with tabs[0]:
    show(line(t, "appointments", "KPI 1: Appointments per month", "Appointments"), "demand")
    yoy = t.dropna(subset=["yoy_pct"])
    if len(yoy):
        fig = px.bar(yoy, x="month_start", y="yoy_pct", title="KPI 2: Change on the same month last year",
                     color_discrete_sequence=[BLUE])
        fig.update_layout(xaxis_title="", yaxis_title="% change", margin=dict(t=60, b=20))
        show(fig, "demand")
    else:
        st.info("No month in the chosen range has a same month a year earlier. Widen the month range.")

# ----------------------------------------------------------------- KPI 3 and 4
with tabs[1]:
    show(line(wait, ["Same-day share", "Long-wait share (over 14 days)"],
              "KPIs 3 and 4: How far ahead people book"), "wait")

# ----------------------------------------------------------------- KPI 5 and 6
with tabs[2]:
    show(line(dna, "dna_rate", "KPI 5: DNA rate (missed appointments)", "% of attended + DNA", [RED]), "dna")
    icb = load("dna_by_icb")
    icb = in_range(icb, first, last).groupby("icb_code", as_index=False)[["attended", "dna"]].sum()
    icb["dna_rate"] = pct(icb["dna"], icb["attended"] + icb["dna"])
    icb = icb.dropna(subset=["dna_rate"]).sort_values("dna_rate", ascending=False)
    # A slider needs min < max, so only show it when there are more than 5 ICBs to choose from.
    if len(icb) > 5:
        top_n = st.slider("How many ICBs to show", 5, len(icb), min(15, len(icb)))
    else:
        top_n = len(icb)
    fig = px.bar(icb.head(top_n).iloc[::-1], x="dna_rate", y="icb_code", orientation="h",
                 title=f"KPI 6: DNA rate by ICB, highest first (top {top_n})", color_discrete_sequence=[RED])
    fig.update_layout(xaxis_title="DNA rate (%)", yaxis_title="ICB code", margin=dict(t=60, b=20))
    show(fig, "icb")

# ----------------------------------------------------------------- KPI 7, 8, 9, 10
with tabs[3]:
    show(line(mix, ["Face-to-face share", "GP share"], "KPIs 7 and 8: Face-to-face share and GP share"), "mode")
    wk = load("weekday_average").copy()
    wk["avg_per_day"] = wk["appointments"] / wk["days"]
    fig = px.bar(wk, x="weekday_name", y="avg_per_day", title="KPI 9: Average appointments per day, by weekday",
                 color_discrete_sequence=[BLUE])
    fig.update_layout(xaxis_title="", yaxis_title="Average per day", margin=dict(t=60, b=20))
    show(fig, "weekday")
    cat = in_range(load("category_monthly"), first, last).copy()
    cat["Network and extended-access share"] = pct(cat["network_extended"], cat["total"])
    if len(cat):
        show(line(cat, "Network and extended-access share", "KPI 10: Network and extended-access share"), "network")

# ----------------------------------------------------------------- KPI 11
with tabs[4]:
    dur = in_range(load("duration_monthly"), first, last).copy()
    dur["Longer than 15 minutes"] = pct(dur["longer_than_15"], dur["known_duration"])
    if len(dur):
        show(line(dur, "Longer than 15 minutes", "KPI 11: Share of consultations longer than 15 minutes"), "duration")
    else:
        st.info("The duration file only covers December 2021 to June 2022. Widen the month range.")

# ----------------------------------------------------------------- KPI 12 and the quality report
with tabs[5]:
    cat = in_range(load("category_monthly"), first, last).copy()
    cat["Unmapped or inconsistent (categories file)"] = pct(cat["data_quality"], cat["total"])
    dur = in_range(load("duration_monthly"), first, last).copy()
    dur["Unknown duration (duration file)"] = pct(dur["unknown_duration"], dur["total"])
    left, right = st.columns(2)
    with left:
        if len(cat):
            left.plotly_chart(line(cat, "Unmapped or inconsistent (categories file)", "KPI 12a: Data-quality share"),
                              width="stretch")
    with right:
        if len(dur):
            right.plotly_chart(line(dur, "Unknown duration (duration file)", "KPI 12b: Unknown duration share"),
                               width="stretch")
    st.caption("Caveat: " + CAVEATS["quality"])

    st.subheader("Pipeline quality checks")
    report = DATA_DIR / "quality_report.json"
    if report.exists():
        data = json.loads(report.read_text())
        st.write("All checks passed." if data.get("all_passed") else "At least one check FAILED.")
        st.dataframe(pd.DataFrame([{"#": c["id"], "Check": c["name"], "Result": "PASS" if c["passed"] else "FAIL",
                                    "Expected": str(c["expected"]), "Actual": str(c["actual"])}
                                   for c in data["checks"]]), hide_index=True, width="stretch")

    st.subheader("Three decisions behind every number")
    for title, text in DECISIONS:
        st.markdown(f"**{title}.** {text}")
