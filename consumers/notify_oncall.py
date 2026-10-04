"""Consumer (DECLARED to dbt as exposure `oncall_pager`): send pages to on-call.

Reads marts.fct_alerts and writes one message per alert to outputs/pages.jsonl,
standing in for a real paging service.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lineage.emit import file, lineage_run, table  # noqa: E402

WAREHOUSE = os.environ.get("DUCKDB_PATH", str(ROOT / "warehouse" / "monitoring.duckdb"))
ALERTS = table("marts", "fct_alerts")
PAGES = file("outputs/pages.jsonl")


def main() -> int:
    with lineage_run("consumers.notify_oncall", inputs=[ALERTS]) as run:
        rows = duckdb.connect(WAREHOUSE, read_only=True).execute("""
            select alert_id, series_id, resource_type, resource_id, metric, alerted_at, peak_z, direction
            from marts.fct_alerts order by alerted_at
        """).fetchall()
        out = ROOT / PAGES[1]
        out.parent.mkdir(exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as f:
            for a_id, s, rtype, rid, metric, at, z, direction in rows:
                f.write(json.dumps({
                    "alert_id": a_id, "series_id": s, "resource": f"{rtype}/{rid}",
                    "summary": f"{metric} {direction} baseline (z={z})", "alerted_at": at.isoformat(),
                }) + "\n")
        run.output(PAGES, columns={
            "alert_id":   [(ALERTS, "alert_id")],
            "series_id":  [(ALERTS, "series_id")],
            "resource":   [(ALERTS, "resource_type"), (ALERTS, "resource_id")],
            "summary":    [(ALERTS, "metric"), (ALERTS, "direction"), (ALERTS, "peak_z")],
            "alerted_at": [(ALERTS, "alerted_at")],
        })
    print(f"{len(rows)} pages -> {PAGES[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
