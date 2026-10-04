"""Consumer (NOT declared to dbt): daily CPU rollup for a capacity dashboard.

A notebook-turned-script that reads the contracted readings directly, not the
alerts. Writes outputs/daily_cpu.csv.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lineage.emit import file, lineage_run, table  # noqa: E402

WAREHOUSE = os.environ.get("DUCKDB_PATH", str(ROOT / "warehouse" / "monitoring.duckdb"))
READINGS = table("intermediate", "int_metrics__contracted")
ROLLUP = file("outputs/daily_cpu.csv")


def main() -> int:
    with lineage_run("consumers.daily_cpu_rollup", inputs=[READINGS]) as run:
        rows = duckdb.connect(WAREHOUSE, read_only=True).execute("""
            select series_id, cast(measured_at as date) as day,
                   round(avg(value), 3) as avg_cpu, round(max(value), 3) as max_cpu
            from intermediate.int_metrics__contracted
            where metric = 'cpu_utilization'
            group by all order by all
        """).fetchall()
        out = ROOT / ROLLUP[1]
        out.parent.mkdir(exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["series_id", "day", "avg_cpu", "max_cpu"])
            w.writerows(rows)
        run.output(ROLLUP, columns={
            "series_id": [(READINGS, "series_id")],
            "day":       [(READINGS, "measured_at")],
            "avg_cpu":   [(READINGS, "value")],
            "max_cpu":   [(READINGS, "value")],
        })
    print(f"{len(rows)} series-days -> {ROLLUP[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
