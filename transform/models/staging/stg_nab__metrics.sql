-- One typed reading per series per timestamp.
--
-- D1 (profiling/DECISIONS.md): on 2014-03-09 the source stamps a whole hour of
-- readings as 03:00:00 on two series (daylight-saving defect). Readings that
-- share a series and timestamp are averaged, and readings_collapsed records how
-- many went in, so the repair stays visible downstream. Raw is left untouched.
--
-- try_cast, not cast: a value that does not parse becomes NULL and is reported
-- row by row by the not-null tests. A hard cast would crash the whole model and
-- every downstream test would ERROR with no failing rows to triage.
with typed as (
    select
        replace(replace(series_file, 'realAWSCloudwatch/', ''), '.csv', '') as series_id,
        try_cast("timestamp" as timestamp)                                     as measured_at,
        try_cast("value" as double)                                            as value
    from {{ source('nab', 'metrics') }}
)

select
    series_id,
    measured_at,
    avg(value)  as value,
    count(*)    as readings_collapsed
from typed
group by series_id, measured_at
