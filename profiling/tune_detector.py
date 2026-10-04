"""Measure the alerting trade-off on clean data before choosing any setting.

Detector: trailing z-score per series. Baseline = the previous 288 readings
(24 h at 5 min), excluding the current one; no score until 288 readings exist.

  z = (value - trailing_mean) / max(trailing_stddev, noise_floor)

Alerting: a reading with |z| > k is a breach. Breaches less than `merge`
minutes apart form one episode. An episode starting within `cooldown` minutes
of the previous episode's end is suppressed. Each remaining episode is one page.

Scored against NAB's labelled windows (DECISIONS.md D3):
  pages/series/day  how often someone is interrupted
  precision         share of pages that start inside a labelled window
  recall            share of labelled windows with at least one page
  control pages     pages on ec2_cpu_utilization_c6585a, which has no anomaly

Run after `dbt build` (reads intermediate.int_metrics__contracted):
  uv run python profiling/tune_detector.py
Writes profiling/reports/detector_tuning.md.
"""

from __future__ import annotations

import itertools
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("DUCKDB_PATH", ROOT / "warehouse" / "monitoring.duckdb"))
REPORT = ROOT / "profiling" / "reports" / "detector_tuning.md"

WARMUP = 288
CONTROL = "ec2_cpu_utilization_c6585a"
GRID = {
    "k": [3, 4, 5, 6],
    "floor": [False, True],   # True: 1 percentage point for percent metrics, none otherwise
    "merge_min": [0, 30],
    "cooldown_min": [0, 60, 240],
}


def main() -> int:
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    rows = con.execute(f"""
        select series_id, unit, measured_at, value,
               avg(value)          over w as mu,
               stddev_samp(value)  over w as sd,
               count(*)            over w as n
        from intermediate.int_metrics__contracted
        window w as (partition by series_id order by measured_at
                     rows between {WARMUP} preceding and 1 preceding)
        order by series_id, measured_at
    """).fetchall()
    windows: dict[str, list] = {}
    for s, a, b in con.execute("select series_id, window_start, window_end from staging.stg_nab__anomaly_windows").fetchall():
        windows.setdefault(s, []).append((a, b))
    series_days = con.execute(
        "select sum(epoch(max_t - min_t)) / 86400 from (select max(measured_at) max_t, min(measured_at) min_t "
        "from staging.stg_nab__metrics group by series_id)").fetchone()[0]
    n_windows = sum(len(v) for v in windows.values())

    def evaluate(k, floor, merge_min, cooldown_min):
        pages, episode, previous_end = [], {}, {}
        for s, unit, t, v, mu, sd, n in rows:
            if n < WARMUP or sd is None:
                continue
            denom = max(sd, 1.0 if (floor and unit == "percent") else 0.0)
            if denom == 0 or abs(v - mu) / denom <= k:
                continue
            ep = episode.get(s)
            if ep and (t - ep[1]).total_seconds() <= merge_min * 60:
                episode[s] = (ep[0], t)          # extends the current episode
                continue
            if ep:
                previous_end[s] = ep[1]
            episode[s] = (t, t)                  # a new episode starts
            if s in previous_end and (t - previous_end[s]).total_seconds() < cooldown_min * 60:
                continue                         # suppressed by cooldown
            pages.append((s, t))
        inside = [p for p in pages if any(a <= p[1] <= b for a, b in windows.get(p[0], []))]
        detected = {(s, i) for s, t in pages for i, (a, b) in enumerate(windows.get(s, [])) if a <= t <= b}
        return {
            "pages": len(pages),
            "per_series_day": len(pages) / series_days,
            "precision": len(inside) / max(len(pages), 1),
            "recall": len(detected) / n_windows,
            "control": sum(1 for s, _ in pages if s == CONTROL),
        }

    out = [
        "# Detector tuning on clean data",
        "",
        f"{series_days:.0f} series-days, 17 series, {n_windows} labelled windows. "
        "Precision and recall are against NAB's labelled windows; control = pages on the series with no labelled anomaly.",
        "",
        "| k | noise floor | merge (min) | cooldown (min) | pages | pages / series / day | precision | recall | control pages |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k, floor, merge_min, cooldown_min in itertools.product(*GRID.values()):
        if merge_min == 0 and cooldown_min > 0:
            continue
        r = evaluate(k, floor, merge_min, cooldown_min)
        out.append(
            f"| {k} | {'yes' if floor else 'no'} | {merge_min} | {cooldown_min} | {r['pages']} | "
            f"{r['per_series_day']:.2f} | {r['precision']:.2f} | {r['recall']:.2f} | {r['control']} |"
        )
    text = "\n".join(out) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"(written to {REPORT.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
