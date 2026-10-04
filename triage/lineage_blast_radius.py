"""Stage 3: estimate the blast radius across tool boundaries, from Marquez.

Stage 2 (triage/dbt_blast_radius.py) stops where dbt's knowledge stops. This
picks up from the same failing test and asks the lineage backend, which also
knows about the code outside dbt that reported itself with OpenLineage.

  1. Root: the failing test (dbt run_results) and the column it protects
     (test config meta.checks_column), as a Marquez dataset field.
  2. Table-level: every job and dataset downstream of the root table.
  3. Column-level: every column downstream of the root column.
  4. Per consumer outside dbt: what each view says, and where they disagree.

  uv run python triage/lineage_blast_radius.py            # Marquez on localhost:5000
  MARQUEZ_API=http://host:5000/api/v1 uv run python triage/lineage_blast_radius.py

Writes triage/reports/lineage_blast_radius.md.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict, deque
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lineage.emit import WAREHOUSE_NAMESPACE  # noqa: E402  same naming as every emitter

API = os.environ.get("MARQUEZ_API", "http://localhost:5000/api/v1")
TARGET = ROOT / "transform" / "target"
REPORT = ROOT / "triage" / "reports" / "lineage_blast_radius.md"


def get(path: str, **params) -> dict:
    r = requests.get(f"{API}/{path}", params=params, timeout=60)
    if r.status_code == 404:
        return {"graph": []}
    r.raise_for_status()
    return r.json()


def is_dbt_job(job_name: str) -> bool:
    return job_name.startswith("dbt-run-") or ".build." in job_name


def short(dataset: str) -> str:
    """monitoring.marts.fct_alerts -> marts.fct_alerts; files stay as they are."""
    return dataset.split(".", 1)[1] if dataset.count(".") >= 2 and "/" not in dataset else dataset


def parse_dataset(node_id: str) -> tuple[str, str]:
    """'dataset:<namespace>:<name>' -> (namespace, name). Namespaces may contain ':'
    (duckdb://...), dataset names never do, so split on the last one."""
    ns, name = node_id.removeprefix("dataset:").rsplit(":", 1)
    return ns, name


def failing_roots() -> list[dict]:
    manifest = json.loads((TARGET / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((TARGET / "run_results.json").read_text(encoding="utf-8"))
    roots = []
    for r in results["results"]:
        if not r["unique_id"].startswith("test.") or r["status"] not in ("warn", "fail", "error"):
            continue
        test = manifest["nodes"][r["unique_id"]]
        model = manifest["nodes"][test["attached_node"]]
        column = test.get("column_name") or test["config"].get("meta", {}).get("checks_column")
        roots.append({
            "test": test["name"], "status": r["status"], "failures": r["failures"],
            "dataset": f"{model['database']}.{model['schema']}.{model['alias']}", "column": column,
        })
    exposed = {  # datasets a dbt exposure depends on
        f"{manifest['nodes'][d]['database']}.{manifest['nodes'][d]['schema']}.{manifest['nodes'][d]['alias']}": e["name"]
        for e in manifest.get("exposures", {}).values() for d in e["depends_on"]["nodes"]
    }
    return roots, exposed


def table_downstream(dataset: str) -> tuple[dict, dict]:
    """Directed walk dataset -> job -> dataset. Returns jobs {name: (inputs, outputs)}, datasets {id: depth}."""
    graph = {n["id"]: n for n in get("lineage", nodeId=f"dataset:{WAREHOUSE_NAMESPACE}:{dataset}", depth=20)["graph"]}
    start = f"dataset:{WAREHOUSE_NAMESPACE}:{dataset}"
    seen, queue, jobs = {start: 0}, deque([start]), {}
    while queue:
        node = queue.popleft()
        for edge in graph.get(node, {}).get("outEdges", []):
            nxt = edge["destination"]
            if nxt not in seen:
                seen[nxt] = seen[node] + 1
                queue.append(nxt)
    for node_id in seen:
        n = graph.get(node_id)
        if n and n["type"] == "JOB":
            ins = [parse_dataset(e["origin"]) for e in n["inEdges"]]
            outs = [parse_dataset(e["destination"]) for e in n["outEdges"]]
            jobs[n["data"]["name"]] = (ins, outs)
    datasets = {k: v for k, v in seen.items() if k.startswith("dataset:")}
    return jobs, datasets


def column_downstream(dataset: str, column: str) -> dict[tuple[str, str], set[str]]:
    """Every (namespace, dataset) -> {fields} reachable downstream of one column."""
    # The longest path in this pipeline is 6 hops (raw -> ... -> pages); 10 covers it.
    nodes = get("column-lineage", nodeId=f"datasetField:{WAREHOUSE_NAMESPACE}:{dataset}:{column}",
                depth=10, withDownstream="true")["graph"]
    children = defaultdict(set)
    for n in nodes:
        d = n["data"]
        me = (d["namespace"], d["dataset"], d["field"])
        for src in d.get("inputFields") or []:
            children[(src["namespace"], src["dataset"], src["field"])].add(me)
    start = (WAREHOUSE_NAMESPACE, dataset, column)
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in children[queue.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    affected = defaultdict(set)
    for ns, ds, f in seen:
        affected[(ns, ds)].add(f)
    return affected


def main() -> int:
    try:
        roots, exposed = failing_roots()
    except FileNotFoundError:
        raise SystemExit("dbt artifacts missing. Run `dbt-ol build ...` first.")
    if not roots:
        print("No failing tests. Nothing to triage.")
        return 0
    try:
        requests.get(f"{API}/namespaces", timeout=5).raise_for_status()
    except Exception as e:
        raise SystemExit(f"Marquez not reachable at {API} ({e}). Is `docker compose up -d` running?")

    lines = ["# Blast radius across tool boundaries, from Marquez", ""]
    say = lines.append
    for root in roots:
        if not root["column"]:
            say(f"_`{root['test']}` names no column (no column_name or meta.checks_column); skipped._")
            continue
        ds, col = root["dataset"], root["column"]
        jobs, datasets = table_downstream(ds)
        cols = column_downstream(ds, col)

        say(f"## Root: `{root['test']}` ({root['status']}, {root['failures']} rows) protects `{short(ds)}.{col}`")
        say("")

        say("### Table-level: everything downstream of the table")
        say("")
        for job, (ins, outs) in sorted(jobs.items(), key=lambda kv: (is_dbt_job(kv[0]) is False, kv[0])):
            kind = "dbt" if is_dbt_job(job) else "**outside dbt**"
            reads = ", ".join(f"`{short(n)}`" for _, n in ins)
            writes = ", ".join(f"`{short(n)}`" for _, n in outs) or "nothing"
            say(f"- {kind} `{job}`: reads {reads} -> writes {writes}")
        say("")

        say(f"### Column-level: everything computed from `{col}`")
        say("")
        for (_, name), fields in sorted(cols.items(), key=lambda kv: kv[0][1]):
            say(f"- `{short(name)}`: {', '.join(sorted(fields))}")
        say("")

        say("### Consumers outside dbt")
        say("")
        say("| consumer | declared to dbt | table-level | column-level | affected output columns |")
        say("|---|---|---|---|---|")
        disagreements = []
        for job, (ins, outs) in sorted(jobs.items()):
            if is_dbt_job(job):
                continue
            declared = next((exposed[name] for _, name in ins if name in exposed), None)
            hit = {name: sorted(cols.get(o, set())) for o in outs for name in [o[1]]}
            hit_cols = [f"`{name}`: {', '.join(c)}" for name, c in hit.items() if c]
            col_verdict = "affected" if hit_cols else "not affected"
            if not hit_cols:
                disagreements.append(job)
            say(f"| `{job}` | {('yes, `' + declared + '`') if declared else 'no'} | affected | {col_verdict} | "
                f"{'; '.join(hit_cols) or '-'} |")
        say("")

        say("### Where the two views disagree")
        say("")
        say("Table-level lineage flags every consumer downstream of the table. Column-level lineage only "
            "follows columns computed *directly* from the bad column; a column whose rows exist *because of* "
            "a filter, join or count on it (an indirect dependency) is not traced. So:")
        say("")
        say("- consumers both views flag are affected;")
        say("- for each consumer only table-level flags, decide which it is: a false alarm (it reads only "
            "columns the fault cannot change), or an indirect dependency column lineage cannot see:")
        for job in disagreements:
            say(f"  - `{job}`")
        say("")

    text = "\n".join(lines) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"(written to {REPORT.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
