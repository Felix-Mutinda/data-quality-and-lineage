# Data quality decisions

Every test, threshold and repair in this repo is justified by the raw profile
(`profiling/reports/raw_profile.md`, produced by `profiling/profile_raw.py`
against NAB `realAWSCloudwatch` at commit `ea702d7`). Nothing here was decided
before looking at the data.

## What the profile showed

| # | Finding | Evidence (profile section) |
|---|---|---|
| F1 | Every row parses: 67,740 rows, no null, blank, unparseable, NaN or infinite timestamp or value. | 1 |
| F2 | Units span up to 10⁸ between series: CPU 0.06–99.9 %, disk writes up to 8.6×10⁸ bytes, ELB 1–656 requests. No negative value anywhere. | 2 |
| F3 | **A real source defect.** On 2014-03-09 (US daylight-saving switch) two series, `ec2_disk_write_bytes_1ef3de` and `ec2_network_in_5abac7`, skip 02:00–02:59 and stamp that hour's 12 readings as `03:00:00`. On the network series the 12 values differ. | 3, follow-up query |
| F4 | Otherwise regular 300 s cadence: 13 single missed samples (600 s), two 15–20 min gaps, longest silence 64 min (the DST hour). | 3 |
| F5 | Long zero runs are normal for some metrics: disk writes sit at 0 for up to 41 h (idle disk); the ASG series is 0 for its last ~3 days and only 37 of those 447 zeros are inside a labelled window. | 2, 4 |
| F6 | For CPU, network and ELB series the longest run of an unchanged value is 8 readings (40 min). Inside the collapsed DST hour the run length depends on row order and can read as up to 1 h. | 4 |
| F7 | Labels are coarse by design: NAB sizes each window to ~10 % of its series. One labelled point (iio, 09:35) sits 1 h before its own window. `ec2_cpu_utilization_c6585a` has no labelled anomaly. | 5 |
| F8 | Two near-idle CPU series (`24ae8d`, `c6585a`) have only 24–29 distinct values: tiny quantised blips that a naive detector will over-alert on. | 2 |

## Decisions

### D1. Repair the DST collapse in staging, not in raw  (F3)

Raw stays byte-for-byte what NAB published. Staging collapses readings that
share `(series, timestamp)` into their **average** and records
`readings_collapsed` (1 for normal rows, 12 for the two DST rows), so the
repair is visible to anyone downstream. No row order is invented.

### D2. Tests on the typed readings, thresholds from the profile

The tests run on `int_metrics__contracted`: the staging readings joined
(left join) to their contract in `seeds/series_catalog.csv`, plus two derived
signals, `seconds_since_previous` and `minutes_unchanged`.

| Test | Scope | Rule | Why this threshold | Baseline |
|---|---|---|---|---|
| Present and parseable | all series | `measured_at` and `value` not null after casting | F1: zero today, so any hit is a real break | pass |
| One reading per series per timestamp | all series | unique `(series_id, measured_at)` | holds after D1 | pass |
| Physical bounds | per metric type, from a seed catalogue | CPU 0–100; bytes, packets, requests ≥ 0 | F2: units differ too much for a global rule | pass |
| No silence | all series | gap to previous reading ≤ 2 h | F4: worst real gap is 64 min; 2 h leaves margin | pass |
| No stuck agent | CPU, network, ELB | value changes at least once in any 2 h | F6: worst real run 40 min (≤ 1 h in DST hour). F5: disk and ASG excluded, long constant runs are normal there | pass |

Bounds and the stuck-agent scope live in a seed (`series_catalog`), not in
SQL, so the contract per metric is data that can be reviewed.

### D3. Labels are ground truth for alerts, used as windows

Alert quality is scored against the labelled **windows** (F7). Labelled points
are kept for reference only. Because windows are ~10 % of each series,
"alert inside a window" is a lenient definition of a true positive; the
article says so. `c6585a` (no labels) is the control series: every alert on it
is noise (F7, F8).

### D4. Scenario: a stuck metrics agent

The injected failure is an agent that keeps re-sending its last value for
several hours on a CPU series. Chosen because the profile shows it is the
failure a range test **cannot** see (a stuck value is a valid value, F2) and
only the stuck-agent test catches (F6). Downstream it produces both
alert-fatigue outcomes, measurable against the labels:

- stuck high: a level shift the detector reads as an anomaly, an alert storm
- stuck during a labelled incident: the real incident is missed

### D5. Severity: structural tests stop the build, behavioural tests warn

Not-null, uniqueness, physical bounds and "every series has a contract" fail
with **error**: a hit means the pipeline itself is wrong, nothing downstream
should be trusted. Silence and stuck-agent fail with **warn**: a hit means one
source is misbehaving, and halting monitoring for the whole fleet because one
agent is stuck would be the worse outcome. That trade-off is the reason
downstream blast radius matters: on a warning, the bad data keeps flowing.

Measured headroom on clean data: longest unchanged run on checked series
35 min (threshold 120), longest silence 64 min (threshold 120).

### D6. Staging uses try_cast, never cast

Found by mutation-testing the tests: with a hard `cast`, one unparseable
timestamp crashed the staging view and every test reported ERROR with no
failing rows. With `try_cast` the bad value becomes NULL and the not-null test
reports the exact row. Every test was checked against an injected defect:

| Injected into raw | Test that fired |
|---|---|
| CPU value 150 | value_within_physical_bounds (FAIL 1) |
| CPU value constant for 3 h | no_stuck_agent_over_2h (WARN 12) |
| 3 h of readings deleted | no_silence_over_2h (WARN 1) |
| series not in the catalogue | every_series_has_a_contract (FAIL 1) |
| unparseable timestamp / value | not-null on measured_at / value (FAIL 1 each) |

Uniqueness cannot be triggered from raw (staging collapses duplicates by
design, D1); it guards that repair against regressions.

### D7. Detector: trailing z-score with a noise floor for percent metrics

Measured in `profiling/reports/detector_tuning.md` (`profiling/tune_detector.py`
over clean data, scored against the labelled windows).

`z = (value - mean) / max(stddev, noise_floor)` over the previous 288 readings
(24 h), no score during warm-up, breach when `|z| > 4`.

- **k = 4.** Against k = 3 it keeps the same recall (0.73) with 30 % fewer
  pages (274 vs 389). k = 5 loses recall (0.67) for 23 % fewer pages.
- **Noise floor of 1 percentage point on percent metrics** (catalogue column
  `noise_floor`). Without it the no-anomaly control series `c6585a` pages 13
  times on ±0.07 % blips (F8); with it, 0. The cost is real and stated: the
  labelled anomalies on the two near-idle CPU series (`24ae8d`, `53ea38`) are
  smaller than 1 point and are no longer detected (recall 0.83 to 0.73).

### D8. Alerting: 30-minute episodes, 60-minute cooldown

Breaches less than 30 min apart are one episode; an episode starting within
60 min of the previous one's end is suppressed. 623 breaches become 353
episodes become **274 pages**: 1.17 pages per series per day, about 20 a day
for this 17-series fleet, with no loss of recall. A 4-hour cooldown would
halve pages again but starts missing incidents (recall 0.70).

What the baseline says about alert fatigue, before any bad data:
**83 % of pages land outside a labelled incident** (precision 0.17), mostly on
bursty byte counters (disk, network) where a z-score is a weak model. That is
the noise floor of this system. The scenario (D4) is measured against it.

### D9. Scenario parameters, chosen by measurement

Every CPU series was tried two ways against the D7/D8 baseline:

1. **Stuck at a normal value through a labelled incident** (2 h before its
   first page to 4 h after its last), 11 runs: up to 2 real pages lost, and
   one labelled incident missed entirely in 6 of 11 runs.
2. **Stuck at the series' peak value** for 6 h and 12 h, 20 runs: **zero extra
   pages in every run.**

So D4's "stuck high produces an alert storm" is **wrong for this system**: the
24 h trailing baseline still holds the earlier variance, so neither the frozen
plateau nor the recovery scores as anomalous. What a stuck agent does here
is make the detector blind, and then miscalibrate it.

Chosen: `ec2_cpu_utilization_fe7f93`, stuck at 2.332 % from
2014-02-17 03:42 to 15:42 (12 h, 145 readings). Through that window the real
host spikes to 60-70 % CPU (NAB labels the anomaly at 06:12).

| | clean | stuck agent |
|---|---|---|
| page for the real incident | 05:42, z = 57.9 | **none** |
| pages on fe7f93, next 24 h after recovery | 0 | **3, none in a labelled window** |
| fleet pages | 274 | 275 |
| labelled incidents paged (recall) | 22 / 30 (0.73) | 21 / 30 (0.70) |
| `no_stuck_agent_over_2h` | pass | **WARN, 122 readings** |
| every other test | pass | pass |

Both alert-fatigue outcomes, from one fault: the incident that mattered was
missed, and on-call was then paged three times for nothing. The only signal
is a warning (D5), so the build succeeds and the bad readings flow on to
every model and consumer downstream. Estimating that blast radius is the
rest of this repo.

### D10. A failing test must say which rows failed

Checked on the D9 scenario: out of the box, the stuck-agent warning stored 122
rows containing only `expression = false`. No series, no timestamp, so the
failure could not be traced to a single reading. dbt-expectations dispatches
`expression_is_true`; the project overrides it
(`transform/macros/triageable_expression_is_true.sql`) so stored failures keep
the whole row. With `minutes_unchanged` in the row, triage can also recover
when the agent actually got stuck (03:37), two hours before the test could see
it (05:37).

### D11. Lineage across tool boundaries: what it took, and what it still misses

OpenLineage events were captured to a file and inspected before Marquez was
involved. Findings, and what was changed because of them:

| Finding | Effect | Change |
|---|---|---|
| dbt-ol names a source by its dbt `name`, ignoring `identifier:` | lineage showed `raw.metrics`, a table that does not exist, so ingestion and dbt would not join | source tables renamed to the real table names |
| Column lineage stops at `select *` | `fct_alerts.peak_z` traced back only to `int_alert_episodes`, not to the reading | every model lists its columns; the chain now runs `raw.nab_metrics.value` to `fct_alerts.peak_z` |
| The SQL parser reports some CTE names (`baseline`, `episodes`) as input datasets | phantom nodes in column lineage | not fixable in SQL; triage ignores names that are not `<db>.<schema>.<table>` |
| dbt-ol emits nothing for seeds | `series_catalog` is invisible; `dim_resources` appears to have no upstream | none; stated as a blind spot of this integration |
| dbt-ol does not read `DBT_PROJECT_DIR` / `DBT_PROFILES_DIR` | fails to find the project | pass `--project-dir transform --profiles-dir transform` |

Code outside dbt reports itself with `lineage/emit.py`, using exactly the
dataset names dbt-ol uses (`duckdb://<profile path>`, `<db>.<schema>.<table>`).
Ingestion and four consumers do so:

| Job | Reads | Declared to dbt? |
|---|---|---|
| `ingest.load_warehouse` | the pinned NAB files | n/a (upstream) |
| `consumers.notify_oncall` | `marts.fct_alerts` | yes, exposure `oncall_pager` |
| `consumers.oncall_noise_report` | `marts.fct_alert_scorecard` | no |
| `consumers.daily_cpu_rollup` | `intermediate.int_metrics__contracted` | no |
| `consumers.resource_inventory` | `intermediate.int_metrics__contracted`, identity columns only | no |

Lineage emission never breaks the job it describes: if the backend is down the
script completes and prints a warning.

### D12. Column lineage needs documented columns, and only sees direct dependencies

Found by querying Marquez (0.51.1) on the D9 scenario:

1. **Undocumented models are column-lineage dead ends.** Marquez keeps a
   column edge only when both ends are columns it knows, and it learns a
   dataset's columns from the `schema` facet, which dbt-ol only sends for
   columns documented in YAML. With `stg_nab__metrics`, `int_metrics__scored`
   and `int_alert_episodes` undocumented, the column graph from
   `raw.nab_metrics.value` came back empty. Every model now documents every
   column, `lineage/emit.py` sends input schemas too (the NAB files), and every
   test names the column it protects (`meta.checks_column`).
2. **Table-level and column-level lineage err in opposite directions.**
   `triage/lineage_blast_radius.py` on the stuck-agent scenario:

   | consumer | table-level | column-level | truth |
   |---|---|---|---|
   | `daily_cpu_rollup` | affected | affected (`avg_cpu`, `max_cpu`) | affected |
   | `notify_oncall` | affected | affected (`summary`) | affected (3 false pages, 1 missing) |
   | `oncall_noise_report` | affected | **not affected** | affected: its page counts changed |
   | `resource_inventory` | **affected** | not affected | not affected: identity columns only |

   Table-level lineage over-reports (`resource_inventory` reads only
   identity columns). Column-level lineage under-reports: it follows only
   direct dependencies, and which pages *exist* depends on `value` through a
   `where is_breach` filter and a `count(*)`, so the noise report is invisible
   to it. The truth sits between the two; the triage reports both and lists
   the disagreements for a human to settle.

### D13. Settle the blast radius with evidence

Lineage predicts; a diff proves. `triage/verify_blast_radius.py` snapshots
every consumer's output after a clean run and compares it with the output
after the stuck-agent run:

| consumer | rows removed | rows added | affected | table-level | column-level |
|---|---|---|---|---|---|
| `daily_cpu_rollup` | 1 | 1 | **yes** | affected | affected |
| `oncall_noise_report` | 1 | 1 | **yes** | affected | not affected |
| `notify_oncall` | 2 | 3 | **yes** | affected | affected |
| `resource_inventory` | 0 | 0 | no | affected | not affected |

- `pages.jsonl`: the real incident page (05:42, z = 57.9) and the 11:42 page
  are gone; three false pages (18:12, 23:22, 06:02) were sent.
- `oncall_noise_report.csv`: fe7f93 goes from 36 pages, 92 % noise, to 37
  pages, 97 % noise; the fault makes a noisy series look noisier.
- `daily_cpu.csv`: 17 Feb average CPU reads 3.3 % instead of 9.3 %.

The verified blast radius is three of four consumers, two of them never
declared to dbt. Table-level lineage over-reported by one
(`resource_inventory`); column-level lineage under-reported by one
(`oncall_noise_report`). Each view alone is wrong in a predictable direction;
read together, with the diff to settle the disagreements, they are right.
