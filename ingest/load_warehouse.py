"""Load the pinned NAB files into a fresh DuckDB warehouse, verbatim.

Everything lands in the `raw` schema as text, exactly as published. Typing,
cleaning and every judgement about the data happen later, in dbt.

  raw.nab_metrics           one row per CSV line: series_file, timestamp, value
  raw.nab_anomaly_windows   one row per labelled window: series_file, window_start, window_end
  raw.nab_anomaly_points    one row per labelled point: series_file, labelled_at

Rerunning it is the reset: the warehouse is deleted and rebuilt from data/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
NAB = ROOT / "data" / "nab"
WAREHOUSE = Path(os.environ.get("DUCKDB_PATH", ROOT / "warehouse" / "monitoring.duckdb"))


def main() -> int:
    manifest = NAB / "MANIFEST.json"
    if not manifest.exists():
        raise SystemExit("data/nab not found. Run `uv run python ingest/fetch_nab.py` first.")
    corpus = json.loads(manifest.read_text())["corpus"]

    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    for f in (WAREHOUSE, Path(f"{WAREHOUSE}.wal")):
        f.unlink(missing_ok=True)

    con = duckdb.connect(str(WAREHOUSE))
    con.execute("create schema raw")

    con.execute(f"""
        create table raw.nab_metrics as
        select
            '{corpus}/' || parse_filename(filename) as series_file,
            "timestamp",
            "value"
        from read_csv(
            '{(NAB / corpus).as_posix()}/*.csv',
            header = true,
            all_varchar = true,
            filename = true
        )
    """)

    windows = json.loads((NAB / "labels" / "combined_windows.json").read_text())
    points = json.loads((NAB / "labels" / "combined_labels.json").read_text())
    con.execute("create table raw.nab_anomaly_windows (series_file varchar, window_start varchar, window_end varchar)")
    con.executemany(
        "insert into raw.nab_anomaly_windows values (?, ?, ?)",
        [(k, s, e) for k, ws in windows.items() if k.startswith(f"{corpus}/") for s, e in ws],
    )
    con.execute("create table raw.nab_anomaly_points (series_file varchar, labelled_at varchar)")
    con.executemany(
        "insert into raw.nab_anomaly_points values (?, ?)",
        [(k, t) for k, ts in points.items() if k.startswith(f"{corpus}/") for t in ts],
    )

    for table in ("nab_metrics", "nab_anomaly_windows", "nab_anomaly_points"):
        n, s = con.execute(f"select count(*), count(distinct series_file) from raw.{table}").fetchone()
        print(f"raw.{table:<20} {n:>6} rows  {s:>2} series")
    print(f"warehouse -> {WAREHOUSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
