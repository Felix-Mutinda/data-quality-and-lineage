# Raw profile: NAB realAWSCloudwatch

## 1. Parseability

Rows whose timestamp or value does not parse, or is null/blank.

| rows | ts_blank | ts_unparseable | value_blank | value_unparseable | value_nan_inf |
|---|---|---|---|---|---|
| 67740 | 0 | 0 | 0 | 0 | 0 |


## 2. Shape

Per series: span and value distribution. Units are implied by the metric name.

| series | rows | first_ts | last_ts | min | p01 | p50 | p99 | max | negatives | zeros | distinct_values |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ec2_cpu_utilization_24ae8d | 4032 | 2014-02-14 14:30:00 | 2014-02-28 14:25:00 | 0.066 | 0.066 | 0.134 | 0.202 | 2.344 | 0 | 0 | 29 |
| ec2_cpu_utilization_53ea38 | 4032 | 2014-02-14 14:30:00 | 2014-02-28 14:25:00 | 1.604 | 1.672 | 1.8 | 2.11 | 2.656 | 0 | 0 | 177 |
| ec2_cpu_utilization_5f5533 | 4032 | 2014-02-14 14:27:00 | 2014-02-28 14:22:00 | 34.77 | 36.67 | 42.92 | 53.37 | 68.09 | 0 | 0 | 2118 |
| ec2_cpu_utilization_77c1ca | 4032 | 2014-04-02 14:25:00 | 2014-04-16 14:20:00 | 0.064 | 0.066 | 0.1 | 99.11 | 99.9 | 0 | 0 | 763 |
| ec2_cpu_utilization_825cc2 | 4032 | 2014-04-10 00:04:00 | 2014-04-24 00:09:00 | 18.72 | 24.79 | 92.45 | 97.17 | 99.12 | 0 | 0 | 1737 |
| ec2_cpu_utilization_ac20cd | 4032 | 2014-04-02 14:29:00 | 2014-04-16 14:49:00 | 2.464 | 2.7 | 34.66 | 99.51 | 99.74 | 0 | 0 | 1934 |
| ec2_cpu_utilization_c6585a | 4032 | 2014-04-02 14:29:00 | 2014-04-16 14:24:00 | 0.062 | 0.066 | 0.066 | 0.136 | 1.602 | 0 | 0 | 24 |
| ec2_cpu_utilization_fe7f93 | 4032 | 2014-02-14 14:27:00 | 2014-02-28 14:22:00 | 1.8 | 1.878 | 2.582 | 64.24 | 99.67 | 0 | 0 | 1470 |
| ec2_disk_write_bytes_1ef3de | 4730 | 2014-03-01 17:34:00 | 2014-03-18 03:39:00 | 0 | 0 | 0 | 1.772e+08 | 5.475e+08 | 0 | 4249 | 448 |
| ec2_disk_write_bytes_c0d644 | 4032 | 2014-04-02 14:25:00 | 2014-04-16 14:20:00 | 0 | 0 | 0 | 5.02e+08 | 8.64e+08 | 0 | 3256 | 677 |
| ec2_network_in_257a54 | 4032 | 2014-04-10 00:04:00 | 2014-04-24 00:09:00 | 3.852e+04 | 1.927e+05 | 2.342e+05 | 3.257e+06 | 2.451e+08 | 0 | 0 | 3938 |
| ec2_network_in_5abac7 | 4730 | 2014-03-01 17:36:00 | 2014-03-18 03:41:00 | 42 | 42 | 68.4 | 5.273e+06 | 8.285e+06 | 0 | 0 | 558 |
| elb_request_count_8c0756 | 4032 | 2014-04-10 00:04:00 | 2014-04-24 00:39:00 | 1 | 2 | 48 | 251.4 | 656 | 0 | 0 | 269 |
| grok_asg_anomaly | 4621 | 2014-01-16 00:00:00 | 2014-02-01 01:00:00 | 0 | 0 | 33.44 | 38.11 | 45.62 | 0 | 447 | 354 |
| iio_us-east-1_i-a2eb1cd9_NetworkIn | 1243 | 2013-10-09 16:25:00 | 2013-10-13 23:55:00 | 7.898e+05 | 8.965e+05 | 3.795e+06 | 2.001e+07 | 6.152e+07 | 0 | 0 | 1243 |
| rds_cpu_utilization_cc0c53 | 4032 | 2014-02-14 14:30:00 | 2014-02-28 14:30:00 | 5.19 | 5.604 | 6.082 | 15.68 | 25.1 | 0 | 0 | 579 |
| rds_cpu_utilization_e47b3b | 4032 | 2014-04-10 00:02:00 | 2014-04-23 23:57:00 | 12.63 | 12.99 | 16.68 | 29.59 | 76.23 | 0 | 0 | 825 |


## 3. Cadence

Seconds between consecutive readings per series (ordered by timestamp).

| series | typical_gap_s | min_gap_s | max_gap_s | duplicate_ts | gaps_over_10min | off_cadence |
|---|---|---|---|---|---|---|
| ec2_cpu_utilization_24ae8d | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_cpu_utilization_53ea38 | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_cpu_utilization_5f5533 | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_cpu_utilization_77c1ca | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_cpu_utilization_825cc2 | 300 | 300 | 600 | 0 | 0 | 2 |
| ec2_cpu_utilization_ac20cd | 300 | 300 | 1200 | 0 | 2 | 2 |
| ec2_cpu_utilization_c6585a | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_cpu_utilization_fe7f93 | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_disk_write_bytes_1ef3de | 300 | 0 | 3660 | 11 | 1 | 2 |
| ec2_disk_write_bytes_c0d644 | 300 | 300 | 300 | 0 | 0 | 0 |
| ec2_network_in_257a54 | 300 | 300 | 600 | 0 | 0 | 2 |
| ec2_network_in_5abac7 | 300 | 0 | 3840 | 11 | 1 | 2 |
| elb_request_count_8c0756 | 300 | 300 | 600 | 0 | 0 | 8 |
| grok_asg_anomaly | 300 | 300 | 300 | 0 | 0 | 0 |
| iio_us-east-1_i-a2eb1cd9_NetworkIn | 300 | 300 | 300 | 0 | 0 | 0 |
| rds_cpu_utilization_cc0c53 | 300 | 300 | 600 | 0 | 0 | 1 |
| rds_cpu_utilization_e47b3b | 300 | 300 | 300 | 0 | 0 | 0 |

Off-cadence intervals, all series combined:

| gap_s | occurrences |
|---|---|
| 0 | 22 |
| 600 | 13 |
| 60 | 1 |
| 240 | 1 |
| 900 | 1 |
| 1200 | 1 |
| 3660 | 1 |
| 3840 | 1 |


## 4. Flatlines

Longest run of consecutive identical values per series, in readings and hours.

| series | longest_run | hours | stuck_value | from_ts |
|---|---|---|---|---|
| ec2_disk_write_bytes_c0d644 | 493 | 41.1 | 0 | 2014-04-12 02:15:00 |
| ec2_disk_write_bytes_1ef3de | 461 | 38.4 | 0 | 2014-03-01 17:34:00 |
| ec2_cpu_utilization_24ae8d | 8 | 0.7 | 0.134 | 2014-02-18 20:45:00 |
| ec2_cpu_utilization_77c1ca | 7 | 0.6 | 0.1 | 2014-04-06 15:40:00 |
| ec2_cpu_utilization_c6585a | 6 | 0.5 | 0.066 | 2014-04-10 05:59:00 |
| ec2_network_in_5abac7 | 5 | 0.4 | 42 | 2014-03-09 03:00:00 |
| grok_asg_anomaly | 5 | 0.4 | 35.83 | 2014-01-28 22:40:00 |
| ec2_cpu_utilization_53ea38 | 4 | 0.3 | 1.766 | 2014-02-21 10:15:00 |
| elb_request_count_8c0756 | 3 | 0.3 | 3 | 2014-04-13 07:09:00 |
| rds_cpu_utilization_cc0c53 | 3 | 0.3 | 6.04 | 2014-02-20 14:35:00 |
| rds_cpu_utilization_e47b3b | 3 | 0.3 | 13.67 | 2014-04-11 04:22:00 |
| ec2_cpu_utilization_5f5533 | 2 | 0.2 | 43.52 | 2014-02-19 10:12:00 |
| ec2_cpu_utilization_825cc2 | 2 | 0.2 | 97.37 | 2014-04-11 04:54:00 |
| ec2_cpu_utilization_ac20cd | 2 | 0.2 | 2.7 | 2014-04-04 05:44:00 |
| ec2_cpu_utilization_fe7f93 | 2 | 0.2 | 2.034 | 2014-02-17 01:32:00 |
| ec2_network_in_257a54 | 1 | 0.1 | 2.516e+05 | 2014-04-10 00:04:00 |
| iio_us-east-1_i-a2eb1cd9_NetworkIn | 1 | 0.1 | 9.927e+06 | 2013-10-09 16:25:00 |


## 5. Labels

Anomaly windows and points against the series they label.

| series | windows | unparseable | inverted | outside_series | avg_window_h | pct_readings_in_windows |
|---|---|---|---|---|---|---|
| ec2_cpu_utilization_24ae8d | 2 | 0 | 0 | 0 | 16.7 | 10 |
| ec2_cpu_utilization_53ea38 | 2 | 0 | 0 | 0 | 16.7 | 10 |
| ec2_cpu_utilization_5f5533 | 2 | 0 | 0 | 0 | 16.7 | 10 |
| ec2_cpu_utilization_77c1ca | 1 | 0 | 0 | 0 | 33.5 | 10 |
| ec2_cpu_utilization_825cc2 | 1 | 0 | 0 | 0 | 28.5 | 8.5 |
| ec2_cpu_utilization_ac20cd | 1 | 0 | 0 | 0 | 33.8 | 10 |
| ec2_cpu_utilization_c6585a | 0 | 0 | 0 | 0 |  | 0 |
| ec2_cpu_utilization_fe7f93 | 3 | 0 | 0 | 0 | 11.2 | 10 |
| ec2_disk_write_bytes_1ef3de | 1 | 0 | 0 | 0 | 39.3 | 10 |
| ec2_disk_write_bytes_c0d644 | 3 | 0 | 0 | 0 | 11.2 | 10 |
| ec2_network_in_257a54 | 1 | 0 | 0 | 0 | 33.5 | 10 |
| ec2_network_in_5abac7 | 2 | 0 | 0 | 0 | 19.7 | 10 |
| elb_request_count_8c0756 | 2 | 0 | 0 | 0 | 16.7 | 10 |
| grok_asg_anomaly | 3 | 0 | 0 | 0 | 12.8 | 10.1 |
| iio_us-east-1_i-a2eb1cd9_NetworkIn | 2 | 0 | 0 | 0 | 5.2 | 10.1 |
| rds_cpu_utilization_cc0c53 | 2 | 0 | 0 | 0 | 16.7 | 10 |
| rds_cpu_utilization_e47b3b | 2 | 0 | 0 | 0 | 16.7 | 10 |

Labelled points that fall outside every window of their series:

| series | labelled_at |
|---|---|
| iio_us-east-1_i-a2eb1cd9_NetworkIn | 2013-10-10 09:35:00 |

