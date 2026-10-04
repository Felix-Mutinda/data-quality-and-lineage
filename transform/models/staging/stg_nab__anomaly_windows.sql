-- NAB's labelled anomaly windows: the ground truth alerts are scored against (D3).
select
    replace(replace(series_file, 'realAWSCloudwatch/', ''), '.csv', '') as series_id,
    try_cast(window_start as timestamp)                                    as window_start,
    try_cast(window_end as timestamp)                                      as window_end
from {{ source('nab', 'anomaly_windows') }}
