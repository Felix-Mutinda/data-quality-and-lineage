-- One row per page: alert episodes that survived the cooldown (D8).
-- This is what the on-call notifier consumes.
select
    e.series_id || '@' || strftime(e.episode_start, '%Y-%m-%dT%H:%M') as alert_id,
    e.series_id,
    r.resource_type,
    r.resource_id,
    r.metric,
    e.episode_start                                         as alerted_at,
    e.episode_end,
    e.breach_count,
    round(e.peak_z, 2)                                      as peak_z,
    case when e.peak_z > 0 then 'above' else 'below' end    as direction
from {{ ref('int_alert_episodes') }} as e
join {{ ref('dim_resources') }} as r using (series_id)
where not e.is_suppressed
