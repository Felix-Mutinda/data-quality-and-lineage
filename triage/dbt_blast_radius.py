"""Stage 2: estimate the blast radius of a failing test using only what dbt knows.

Inputs are artifacts dbt writes on every run, plus the stored failing rows:

  transform/target/run_results.json   which tests warned or failed
  transform/target/manifest.json      the DAG (child_map), tests, exposures
  test_failures.<test>                the failing rows (store_failures)

Triage order:
  1. What failed? Which failure is the root, which are echoes of it?
  2. Which rows are bad: which series, since when, until when?
  3. What is downstream inside dbt, and which of its rows are touched?
  4. Which declared consumers (exposures) sit downstream, and who owns them?
  5. Where does dbt's view end?

  uv run python triage/dbt_blast_radius.py
Writes triage/reports/dbt_blast_radius.md.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import deque
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "transform" / "target"
WAREHOUSE = Path(os.environ.get("DUCKDB_PATH", ROOT / "warehouse" / "monitoring.duckdb"))
REPORT = ROOT / "triage" / "reports" / "dbt_blast_radius.md"

CADENCE = dt.timedelta(minutes=5)  # profiling F4
TIME_COLUMNS = ("measured_at", "episode_start", "alerted_at")


def load(name: str) -> dict:
    path = TARGET / name
    if not path.exists():
        raise SystemExit(f"{path} missing. Run `dbt build` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def downstream(start: str, child_map: dict) -> list[tuple[str, int]]:
    """Breadth-first walk of the DAG from `start`: (node, depth)."""
    seen, out, queue = {start}, [], deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        for child in child_map.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append((child, depth + 1))
                queue.append((child, depth + 1))
    return out


def main() -> int:
    manifest, results = load("manifest.json"), load("run_results.json")
    nodes, child_map, exposures = manifest["nodes"], manifest["child_map"], manifest.get("exposures", {})
    status = {r["unique_id"]: r for r in results["results"]}
    project_vars = yaml.safe_load((ROOT / "transform" / "dbt_project.yml").read_text())["vars"]
    horizon = CADENCE * int(project_vars["detector_baseline_readings"])

    failing = [(u, r) for u, r in status.items()
               if u.startswith("test.") and r["status"] in ("warn", "fail", "error")]
    if not failing:
        print("All tests passed. Nothing to triage.")
        return 0

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    lines: list[str] = ["# Blast radius, as seen from dbt", ""]
    say = lines.append

    # ---- 1. what failed; root vs echo --------------------------------------
    tested = {u: nodes[u]["attached_node"] for u, _ in failing}
    reach = {m: {n for n, _ in downstream(m, child_map)} for m in set(tested.values())}
    roots = [u for u in tested if not any(tested[u] in reach[tested[o]] for o in tested if o != u)]

    say("## 1. What failed")
    say("")
    say("| test | on model | severity | failing rows | role |")
    say("|---|---|---|---|---|")
    for u, r in failing:
        n = nodes[u]
        say(f"| `{n['name']}` | `{nodes[n['attached_node']]['name']}` | {r['status']} | {r['failures']} | "
            f"{'**root**' if u in roots else 'echo of an upstream failure'} |")
    say("")

    for root in roots:
        test, model_uid = nodes[root], nodes[root]["attached_node"]
        relation = test.get("relation_name")

        # ---- 2. the bad rows -----------------------------------------------
        say(f"## 2. The bad rows behind `{test['name']}`")
        say("")
        bad: list[tuple] = []
        if not relation:
            say("_store_failures is off: dbt knows how many rows failed, not which._")
        else:
            cols = {c[0] for c in con.execute(f"describe {relation}").fetchall()}
            if not {"series_id", "measured_at"} <= cols:
                say(f"_`{relation}` holds no row identity (columns: {', '.join(sorted(cols))}). "
                    "The failure cannot be traced to readings._")
            else:
                # minutes_unchanged lets us recover when the run started, before the test could see it
                start_expr = ("min(measured_at - to_minutes(minutes_unchanged::bigint))"
                              if "minutes_unchanged" in cols else "min(measured_at)")
                bad = con.execute(f"""
                    select series_id, {start_expr} as bad_from, min(measured_at) as first_failing,
                           max(measured_at) as bad_until, count(*) as failing_rows,
                           count(distinct value) as distinct_values, any_value(value) as sample_value
                    from {relation} group by series_id order by series_id
                """).fetchall()
                say(f"From `{relation}`:")
                say("")
                say("| series | bad from | first failing row | bad until | failing rows | distinct values |")
                say("|---|---|---|---|---|---|")
                for s, f, ff, u, n, d, v in bad:
                    say(f"| `{s}` | {f} | {ff} | {u} | {n} | {d} (`{v}`) |")
                say("")
                if "minutes_unchanged" in cols:
                    say("_`bad from` is reconstructed from `minutes_unchanged`: the readings were already wrong "
                        "before the test could tell, because a constant value only becomes suspicious after 2 h._")
        say("")

        # ---- 3. downstream inside dbt ----------------------------------------
        say(f"## 3. Downstream of `{nodes[model_uid]['name']}` inside dbt")
        say("")
        hours = horizon.total_seconds() / 3600
        say(f"Rows touched = rows of the affected series inside the bad window, and inside the "
            f"following {hours:g} h (`detector_baseline_readings` x 5 min), because scoring looks back that far.")
        say("")
        say(f"| depth | model | rebuilt this run | rows in bad window | rows in the following {hours:g} h | other rows of the series |")
        say("|---|---|---|---|---|---|")
        reached = downstream(model_uid, child_map)
        for uid, depth in reached:
            if not uid.startswith("model."):
                continue
            n = nodes[uid]
            rel = n.get("relation_name")
            cols = {c[0] for c in con.execute(f"describe {rel}").fetchall()} if rel else set()
            rebuilt = "yes" if status.get(uid, {}).get("status") == "success" else "no"
            cells = ["n/a", "n/a", "n/a"]
            tcol = next((c for c in TIME_COLUMNS if c in cols), None)
            if bad and "series_id" in cols:
                in_bad = after = other = 0
                for s, f, _, u, *_ in bad:
                    if tcol:
                        in_bad += con.execute(f"select count(*) from {rel} where series_id=? and {tcol} between ? and ?", [s, f, u]).fetchone()[0]
                        after += con.execute(f"select count(*) from {rel} where series_id=? and {tcol} > ? and {tcol} <= ?", [s, u, u + horizon]).fetchone()[0]
                        other += con.execute(f"select count(*) from {rel} where series_id=? and ({tcol} < ? or {tcol} > ?)", [s, f, u + horizon]).fetchone()[0]
                    else:
                        other += con.execute(f"select count(*) from {rel} where series_id=?", [s]).fetchone()[0]
                cells = [str(in_bad), str(after), str(other) + ("" if tcol else " (whole-series aggregate)")]
            say(f"| {depth} | `{n['name']}` | {rebuilt} | " + " | ".join(cells) + " |")
        say("")

        # ---- 4. declared consumers -------------------------------------------
        say("## 4. Declared consumers (exposures) downstream")
        say("")
        exp = [(u, d) for u, d in reached if u.startswith("exposure.")]
        for uid, depth in exp or []:
            e, o = exposures[uid], exposures[uid].get("owner", {})
            say(f"- **{e.get('label') or e['name']}** ({e['type']}, maturity {e.get('maturity', '?')}), "
                f"depth {depth}, owner {o.get('name', '?')} <{o.get('email', '?')}>")
            for dep in e["depends_on"]["nodes"]:
                rel = nodes[dep]["relation_name"]
                for s, f, _, u, *_ in bad:
                    rows = con.execute(f"select alerted_at from {rel} where series_id=? and alerted_at between ? and ? order by 1",
                                       [s, f, u + horizon]).fetchall()
                    say(f"  - `{nodes[dep]['name']}` rows for `{s}` from {f} to {u + horizon}: "
                        + (", ".join(str(r[0]) for r in rows) if rows else "none"))
        if not exp:
            say("- none declared")
        say("")

    # ---- 5. the edge of dbt's view -------------------------------------------
    say("## 5. Where dbt's view ends")
    say("")
    say("- **Time.** The DAG says which models depend on which. It does not say that a score looks back "
        "24 h, so the 24 h after the bad window had to be added by hand from a project variable.")
    say("- **Absence.** A page that *should* exist and does not leaves no row to find. Section 3 can count "
        "rows that are there; it cannot show the page that was never sent.")
    say("- **Columns.** dbt Core lineage is model to model. A downstream model is listed whether or not it "
        "reads the bad column.")
    say("- **Undeclared consumers.** Only exposures someone wrote down appear in section 4. Scripts, "
        "notebooks, dashboards and jobs in other tools that read these tables are invisible to dbt.")

    text = "\n".join(lines) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"(written to {REPORT.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
