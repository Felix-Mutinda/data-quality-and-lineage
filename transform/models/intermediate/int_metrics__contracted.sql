-- Every typed reading, joined to its series contract (seeds/series_catalog.csv),
-- plus the two derived signals the behavioural tests need (D2):
--   seconds_since_previous   silence before this reading
--   minutes_unchanged        how long the value has been identical up to this reading
--
-- LEFT join on purpose: a series missing from the catalogue must surface as a
-- test failure (null metric), not silently disappear.
with readings as (
    select
        m.*,
        c.resource_type,
        c.resource_id,
        c.metric,
        c.unit,
        c.min_value,
        c.max_value,
        c.stuck_check,
        c.noise_floor,
        lag(m.measured_at) over w as previous_measured_at,
        lag(m.value)       over w as previous_value
    from {{ ref('stg_nab__metrics') }} as m
    left join {{ ref('series_catalog') }} as c using (series_id)
    window w as (partition by m.series_id order by m.measured_at)
),

runs as (
    select
        *,
        -- a new run starts whenever the value differs from the previous reading
        sum(case when value is distinct from previous_value then 1 else 0 end)
            over (partition by series_id order by measured_at) as value_run_id
    from readings
)

select
    series_id,
    measured_at,
    value,
    readings_collapsed,
    resource_type,
    resource_id,
    metric,
    unit,
    min_value,
    max_value,
    stuck_check,
    noise_floor,
    epoch(measured_at - previous_measured_at)::integer as seconds_since_previous,
    (epoch(measured_at - min(measured_at) over (partition by series_id, value_run_id)) / 60)::integer
        as minutes_unchanged
from runs
