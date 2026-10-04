"""Fetch the NAB AWS CloudWatch series and their anomaly labels, pinned to one commit.

Numenta Anomaly Benchmark (MIT licence): https://github.com/numenta/NAB

Writes, verbatim:
  data/nab/realAWSCloudwatch/*.csv      timestamp,value at 5-minute resolution
  data/nab/labels/combined_windows.json labelled anomaly windows per series
  data/nab/labels/combined_labels.json  labelled anomaly points per series
  data/nab/MANIFEST.json                commit, url and sha256 of every file

Small (~2 MB) and committed to the repo, so readers never need the network.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import requests

COMMIT = "ea702d75cc2258d9d7dd35ca8e5e2539d71f3140"  # numenta/NAB master, 2024-12-03
RAW = f"https://raw.githubusercontent.com/numenta/NAB/{COMMIT}"
CORPUS = "realAWSCloudwatch"
LABEL_FILES = ["labels/combined_windows.json", "labels/combined_labels.json"]

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nab"


def fetch(http: requests.Session, rel: str) -> dict:
    target = OUT / rel.removeprefix("data/")
    if not target.exists():
        r = http.get(f"{RAW}/{rel}", timeout=60)
        r.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(r.content)
    return {
        "path": target.relative_to(ROOT).as_posix(),
        "url": f"{RAW}/{rel}",
        "bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def main() -> int:
    files = []
    with requests.Session() as http:
        for rel in LABEL_FILES:
            files.append(fetch(http, rel))
        # The labels file names every series in the corpus; no repo listing needed.
        windows = json.loads((OUT / "labels" / "combined_windows.json").read_text())
        series = sorted(k for k in windows if k.startswith(f"{CORPUS}/"))
        for key in series:
            files.append(fetch(http, f"data/{key}"))
            print(f"ok  {key}")

    manifest_path = OUT / "MANIFEST.json"
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("files") == files:   # nothing changed: keep the file byte-identical
            fetched_at = previous["fetched_at"]
    manifest_path.write_text(json.dumps({
        "source": "Numenta Anomaly Benchmark (NAB), MIT licence",
        "repo": "https://github.com/numenta/NAB",
        "commit": COMMIT,
        "corpus": CORPUS,
        "fetched_at": fetched_at,
        "files": files,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\n{len(series)} series + {len(LABEL_FILES)} label files -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
