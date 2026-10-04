"""Profile the raw NAB tables before writing a single test.

Every test and threshold in transform/ is decided from what this prints, not
from assumptions. Run it after ingest/load_warehouse.py:

  uv run python profiling/profile_raw.py

Writes the same output to profiling/reports/raw_profile.md.

Sections
  1. Parseability   do timestamps and values parse? nulls? blanks?
  2. Shape          rows, time span, value distribution per series
  3. Cadence        sampling interval, gaps, duplicate timestamps
  4. Flatlines      longest run of an unchanged value (stuck agent?)
  5. Labels         are the anomaly windows/points well-formed and inside the series?
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("DUCKDB_PATH", ROOT / "warehouse" / "monitoring.duckdb"))
REPORT = ROOT / "profiling" / "reports" / "raw_profile.md"

out: list[str] = []


def section(title: str, note: str = "") -> None:
    out.extend(["", f"## {title}", ""])
    if note:
        out.extend([note, ""])


def table(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    rel = con.sql(sql)
    cols, rows = rel.columns, rel.fetchall()
    out.append("| " + " | ".join(cols) + " |")
    out.append("|" + "---|" * len(cols))
    for r in rows:
        out.append("| " + " | ".join("" if v is None else (f"{v:.4g}" if isinstance(v, float) else str(v)) for v in r) + " |")
    out.append("")


def main() -> int:
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    out.append("# Raw profile: NAB realAWSCloudwatch")

    # A typed, ordered view used by everything below. try_cast: nothing is assumed parseable.
    con.execute("""
        create temp view m as
        select
            replace(replace(series_file, 'realAWSCloudwatch/', ''), '.csv', '') as series,
            "timestamp" as ts_raw,
            "value"     as value_raw,
            try_cast("timestamp" as timestamp) as ts,
            try_cast("value" as double)        as value
        from raw.nab_metrics
    """)

    section("1. Parseability", "Rows whose timestamp or value does not parse, or is null/blank.")
    table(con, """
        select
            count(*)                                               as rows,
            count(*) filter (where ts_raw is null or trim(ts_raw) = '')       as ts_blank,
            count(*) filter (where ts is null and ts_raw is not null)         as ts_unparseable,
            count(*) filter (where value_raw is null or trim(value_raw) = '') as value_blank,
            count(*) filter (where value is null and value_raw is not null)   as value_unparseable,
            count(*) filter (where isnan(value) or isinf(value))              as value_nan_inf
        from m
    """)

    section("2. Shape", "Per series: span and value distribution. Units are implied by the metric name.")
    table(con, """
        select
            series,
            count(*)                          as rows,
            min(ts)                           as first_ts,
            max(ts)                           as last_ts,
            round(min(value), 4)              as min,
            round(quantile_cont(value, 0.01), 4) as p01,
            round(median(value), 4)           as p50,
            round(quantile_cont(value, 0.99), 4) as p99,
            round(max(value), 4)              as max,
            count(*) filter (where value < 0) as negatives,
            count(*) filter (where value = 0) as zeros,
            count(distinct value)             as distinct_values
        from m
        group by series
        order by series
    """)

    section("3. Cadence", "Seconds between consecutive readings per series (ordered by timestamp).")
    con.execute("""
        create temp view gaps as
        select series, ts,
               epoch(ts - lag(ts) over (partition by series order by ts, value)) as gap_s
        from m
    """)
    table(con, """
        select
            series,
            mode(gap_s)                                        as typical_gap_s,
            min(gap_s)                                         as min_gap_s,
            max(gap_s)                                         as max_gap_s,
            count(*) filter (where gap_s = 0)                  as duplicate_ts,
            count(*) filter (where gap_s > 2 * 300)            as gaps_over_10min,
            count(*) filter (where gap_s not in (300) and gap_s > 0) as off_cadence
        from gaps
        group by series
        order by series
    """)
    out.append("Off-cadence intervals, all series combined:")
    out.append("")
    table(con, """
        select gap_s, count(*) as occurrences
        from gaps where gap_s is not null and gap_s <> 300
        group by gap_s order by occurrences desc, gap_s limit 15
    """)

    section("4. Flatlines", "Longest run of consecutive identical values per series, in readings and hours.")
    table(con, """
        with runs as (
            select series, ts, value,
                   sum(case when value is distinct from prev then 1 else 0 end)
                       over (partition by series order by ts, value) as run_id
            from (select *, lag(value) over (partition by series order by ts, value) as prev from m)
        ), lengths as (
            select series, run_id, any_value(value) as value, count(*) as readings,
                   min(ts) as from_ts, max(ts) as to_ts
            from runs group by series, run_id
        )
        select series,
               readings                          as longest_run,
               round(readings * 5 / 60.0, 1)     as hours,
               value                             as stuck_value,
               from_ts
        from lengths
        -- ties: earliest run wins, so the report is identical on every run
        qualify row_number() over (partition by series order by readings desc, from_ts) = 1
        order by longest_run desc, series
    """)

    section("5. Labels", "Anomaly windows and points against the series they label.")
    con.execute("""
        create temp view w as
        select replace(replace(series_file, 'realAWSCloudwatch/', ''), '.csv', '') as series,
               try_cast(window_start as timestamp) as ws, try_cast(window_end as timestamp) as we,
               window_start, window_end
        from raw.nab_anomaly_windows
    """)
    table(con, """
        with span as (select series, min(ts) as first_ts, max(ts) as last_ts, count(*) as n from m group by series)
        select s.series,
               count(w.ws)                                                    as windows,
               count(*) filter (where w.window_start is not null and w.ws is null) as unparseable,
               count(*) filter (where w.we <= w.ws)                           as inverted,
               count(*) filter (where w.ws < s.first_ts or w.we > s.last_ts)  as outside_series,
               round(avg(epoch(w.we - w.ws)) / 3600, 1)                       as avg_window_h,
               round(100.0 * (select count(*) from m join w w2 using (series)
                              where m.series = s.series and m.ts between w2.ws and w2.we) / s.n, 1)
                                                                              as pct_readings_in_windows
        from span s left join w using (series)
        group by s.series, s.n
        order by s.series
    """)
    out.append("Labelled points that fall outside every window of their series:")
    out.append("")
    table(con, """
        select replace(replace(p.series_file, 'realAWSCloudwatch/', ''), '.csv', '') as series,
               p.labelled_at
        from raw.nab_anomaly_points p
        where not exists (
            select 1 from w
            where w.series = replace(replace(p.series_file, 'realAWSCloudwatch/', ''), '.csv', '')
              and try_cast(p.labelled_at as timestamp) between w.ws and w.we)
    """)

    text = "\n".join(out) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"(written to {REPORT.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
