"""Scenario D4: a metrics agent gets stuck and keeps re-sending its last value.

From `--from` until `--until`, every reading of `--series` in raw is replaced by
the last value the agent reported before `--from`, exactly as a hung agent
replaying its cache would do. Timestamps keep arriving on cadence, so nothing
looks missing; only the values stop moving.

The change is applied upstream, in raw.nab_metrics, like a real provider
fault. `uv run python ingest/load_warehouse.py` undoes it.

  uv run python scenarios/stuck_agent.py                     # the article's scenario
  uv run python scenarios/stuck_agent.py --series ... --from ... --until ...

Writes scenarios/.last_break.json describing what was done.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = Path(os.environ.get("DUCKDB_PATH", ROOT / "warehouse" / "monitoring.duckdb"))
STATE = ROOT / "scenarios" / ".last_break.json"

# Chosen in profiling/DECISIONS.md (D9): the agent hangs 2.5 h before a real,
# labelled CPU incident and stays stuck for 12 h, through all of it.
DEFAULT = {
    "series": "ec2_cpu_utilization_fe7f93",
    "from": "2014-02-17 03:42:00",
    "until": "2014-02-17 15:42:00",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", default=DEFAULT["series"])
    ap.add_argument("--from", dest="start", default=DEFAULT["from"])
    ap.add_argument("--until", dest="end", default=DEFAULT["until"])
    args = ap.parse_args()
    series_file = f"realAWSCloudwatch/{args.series}.csv"

    con = duckdb.connect(str(WAREHOUSE))
    last = con.execute(
        """
        select "timestamp", "value" from raw.nab_metrics
        where series_file = ? and "timestamp" < ?
        order by "timestamp" desc limit 1
        """,
        [series_file, args.start],
    ).fetchone()
    if last is None:
        raise SystemExit(f"No reading of {args.series} before {args.start}.")
    stuck_at, stuck_value = last

    changed = con.execute(
        """
        update raw.nab_metrics set "value" = ?
        where series_file = ? and "timestamp" >= ? and "timestamp" <= ? and "value" <> ?
        """,
        [stuck_value, series_file, args.start, args.end, stuck_value],
    ).fetchone()[0]
    readings = con.execute(
        """select count(*) from raw.nab_metrics
           where series_file = ? and "timestamp" >= ? and "timestamp" <= ?""",
        [series_file, args.start, args.end],
    ).fetchone()[0]

    state = {
        "scenario": "stuck_agent",
        "series_id": args.series,
        "stuck_from": args.start,
        "stuck_until": args.end,
        "stuck_value": stuck_value,
        "last_good_reading_at": stuck_at,
        "readings_in_window": readings,
        "readings_changed": changed,
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        f"{args.series}: agent stuck at {stuck_value} (last good reading {stuck_at}) "
        f"from {args.start} to {args.end}; {readings} readings, {changed} values replaced."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
