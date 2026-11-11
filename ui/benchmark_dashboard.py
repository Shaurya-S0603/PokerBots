import json
from math import isfinite
from pathlib import Path

import streamlit as st

BUNDLED_REPORT = Path(__file__).resolve().parents[1] / "benchmarks" / "evaluation.json"
METRICS = {
  "bb_per_100": "bb/100", "hands": "Hands", "illegal_actions": "Illegal actions",
  "decision_ms_median": "Median ms", "decision_ms_p95": "p95 ms",
  "vpip": "VPIP", "pfr": "PFR",
}


def _metric(value):
  if value is None:
    return "—"
  if type(value) not in (int, float) or not isfinite(value):
    raise ValueError("Expected finite numeric benchmark metrics")
  return value


def _rows(report):
  if not isinstance(report, dict) or report.get("schema_version") != 1:
    raise ValueError("Expected a PokerRoom benchmark report with schema version 1")
  if not isinstance(report.get("config"), dict) or not isinstance(report.get("results"), list):
    raise ValueError("The report must contain a configuration and results")
  rows = []
  for result in report["results"]:
    if not isinstance(result, dict) or not isinstance(result.get("opponent"), str):
      raise ValueError("Each result must name its opponent")
    interval = result.get("interval_95")
    if interval is not None and (not isinstance(interval, list) or len(interval) != 2
        or any(type(bound) not in (int, float) or not isfinite(bound) for bound in interval)):
      raise ValueError("Expected two finite confidence interval bounds")
    row = {"Opponent": result["opponent"]}
    for key, label in METRICS.items():
      if key not in result:
        raise ValueError(f"Missing benchmark metric: {key}")
      value = _metric(result[key])
      if key in {"vpip", "pfr"} and value != "—":
        value = f"{value:.1%}"
      elif type(value) is float:
        value = round(value, 2)
      row[label] = value
    row["95% interval"] = f"{interval[0]:.2f} to {interval[1]:.2f}" if interval else "—"
    rows.append(row)
  return rows


def render_benchmarks():
  st.title("Bot benchmarks")
  st.caption("Equity against the frozen Update 4 strategies in paired heads-up hands.")
  uploaded = st.file_uploader("Load a saved benchmark report (JSON)", type="json")
  try:
    if uploaded and uploaded.size > 10_000_000:
      raise ValueError("Choose a benchmark report under 10 MB")
    raw = uploaded.getvalue() if uploaded else BUNDLED_REPORT.read_bytes()
    report = json.loads(raw)
    rows = _rows(report)
  except (OSError, ValueError) as error:
    st.error(f"Could not load benchmark results. {error}")
    return
  st.dataframe(rows, hide_index=True, use_container_width=True,
    column_order=["Opponent", "bb/100", "95% interval", "Hands", "Illegal actions",
      "Median ms", "p95 ms", "VPIP", "PFR"])
  st.caption("An interval spanning zero leaves the direction of the edge inconclusive. Timing reflects the machine that ran the benchmark.")
  if any(row["Illegal actions"] not in (0, "—") for row in rows):
    st.warning("This run had illegal actions. Incomplete pairs are excluded from the performance estimates.")
  with st.expander("Run configuration"):
    st.json(report["config"])
  st.download_button("Download benchmark report", raw, file_name="pokerroom-benchmark.json",
    mime="application/json")
