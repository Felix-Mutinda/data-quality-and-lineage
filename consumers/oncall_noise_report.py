"""Consumer (NOT declared to dbt): weekly on-call noise report.

Someone on the SRE team ranks series by how noisy their pages are. Reads
marts.fct_alert_scorecard, writes outputs/oncall_noise_report.csv.
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
SCORECARD = table("marts", "fct_alert_scorecard")
REPORT = file("outputs/oncall_noise_report.csv")


def main() -> int:
    with lineage_run("consumers.oncall_noise_report", inputs=[SCORECARD]) as run:
        rows = duckdb.connect(WAREHOUSE, read_only=True).execute("""
            select series_id, pages, pages_per_day,
                   round(1 - pages_in_labelled_window / nullif(pages, 0), 2) as noise_share
            from marts.fct_alert_scorecard
            order by pages_per_day desc, series_id
        """).fetchall()
        out = ROOT / REPORT[1]
        out.parent.mkdir(exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["series_id", "pages", "pages_per_day", "noise_share"])
            w.writerows(rows)
        run.output(REPORT, columns={
            "series_id":     [(SCORECARD, "series_id")],
            "pages":         [(SCORECARD, "pages")],
            "pages_per_day": [(SCORECARD, "pages_per_day")],
            "noise_share":   [(SCORECARD, "pages"), (SCORECARD, "pages_in_labelled_window")],
        })
    print(f"{len(rows)} series -> {REPORT[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
