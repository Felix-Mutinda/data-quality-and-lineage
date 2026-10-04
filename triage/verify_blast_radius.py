"""Stage 4: settle the blast radius with evidence.

Lineage predicts which consumers a fault reaches. This measures it: snapshot
every consumer's output on clean data, rerun on the faulty data, and diff.

  uv run python triage/verify_blast_radius.py snapshot   # after a clean run
  uv run python triage/verify_blast_radius.py compare    # after the incident run

Which job wrote each output is looked up in Marquez, from the lineage each
consumer reported. Writes triage/reports/verified_blast_radius.md.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
CLEAN = OUTPUTS / "_clean"
API = os.environ.get("MARQUEZ_API", "http://localhost:5000/api/v1")
REPORT = ROOT / "triage" / "reports" / "verified_blast_radius.md"


def output_files() -> list[Path]:
    return sorted(p for p in OUTPUTS.glob("*") if p.is_file())


def writer(output: str) -> str:
    """The job that wrote a file, from Marquez's lineage graph."""
    node = f"dataset:file:{output}"
    try:
        graph = requests.get(f"{API}/lineage", params={"nodeId": node, "depth": 1}, timeout=30).json()["graph"]
    except Exception:
        return "?"
    jobs = [n["data"]["name"] for n in graph
            if n["type"] == "JOB" and any(e["destination"] == node for e in n["outEdges"])]
    return jobs[0] if jobs else "?"


def rows(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[1:] if path.suffix == ".csv" else lines   # drop CSV header


def snapshot() -> int:
    files = output_files()
    if not files:
        raise SystemExit("outputs/ is empty. Run the consumers on clean data first.")
    shutil.rmtree(CLEAN, ignore_errors=True)
    CLEAN.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, CLEAN / f.name)
    print(f"snapshot of {len(files)} clean outputs -> {CLEAN.relative_to(ROOT)}")
    return 0


def compare() -> int:
    if not CLEAN.exists():
        raise SystemExit("No clean snapshot. Run `verify_blast_radius.py snapshot` after a clean run.")
    lines = ["# Verified blast radius: clean vs incident outputs", "",
             "| consumer | output | rows removed | rows added | affected |", "|---|---|---|---|---|"]
    details = []
    for clean in sorted(CLEAN.glob("*")):
        now = OUTPUTS / clean.name
        before, after = set(rows(clean)), set(rows(now)) if now.exists() else set()
        removed, added = sorted(before - after), sorted(after - before)
        job = writer(f"outputs/{clean.name}")
        lines.append(f"| `{job}` | `outputs/{clean.name}` | {len(removed)} | {len(added)} | "
                     f"{'**yes**' if removed or added else 'no'} |")
        if removed or added:
            details += ["", f"### `outputs/{clean.name}`", ""]
            details += [f"- removed: `{r}`" for r in removed] + [f"- added: `{a}`" for a in added]
    text = "\n".join(lines + details) + "\n"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(f"(written to {REPORT.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    cmds = {"snapshot": snapshot, "compare": compare}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        raise SystemExit(__doc__)
    raise SystemExit(cmds[sys.argv[1]]())
