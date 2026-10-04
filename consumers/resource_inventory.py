"""Consumer (NOT declared to dbt): monitored-resource inventory for finance.

Counts what is monitored, by resource type. Someone wrote it against the big
readings table because it was there, but it only reads identity columns,
never a measured value. Writes outputs/resource_inventory.csv.
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
INVENTORY = file("outputs/resource_inventory.csv")


def main() -> int:
    with lineage_run("consumers.resource_inventory", inputs=[READINGS]) as run:
        rows = duckdb.connect(WAREHOUSE, read_only=True).execute("""
            select resource_type, count(distinct resource_id) as resources, count(distinct series_id) as series
            from intermediate.int_metrics__contracted group by all order by all
        """).fetchall()
        out = ROOT / INVENTORY[1]
        out.parent.mkdir(exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["resource_type", "resources", "series"])
            w.writerows(rows)
        run.output(INVENTORY, columns={
            "resource_type": [(READINGS, "resource_type")],
            "resources":     [(READINGS, "resource_id")],
            "series":        [(READINGS, "series_id")],
        })
    print(f"{len(rows)} resource types -> {INVENTORY[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
