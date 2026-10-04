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
