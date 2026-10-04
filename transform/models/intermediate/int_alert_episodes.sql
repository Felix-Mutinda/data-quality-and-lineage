-- Alerting (D8): consecutive breaches less than alert_merge_minutes apart are
-- one episode; an episode starting within alert_cooldown_minutes of the
-- previous episode's end is suppressed. Every episode is kept here, suppressed
-- or not, so the effect of the rules stays measurable.
with breaches as (
    select
        series_id,
        measured_at,
        z_score,
        lag(measured_at) over (partition by series_id order by measured_at) as previous_breach_at
    from {{ ref('int_metrics__scored') }}
    where is_breach
),

numbered as (
    select
        series_id,
        measured_at,
        z_score,
        sum(case
                when previous_breach_at is null
                  or epoch(measured_at - previous_breach_at) > {{ var('alert_merge_minutes') }} * 60
                then 1 else 0
            end) over (partition by series_id order by measured_at) as episode_no
    from breaches
),

episodes as (
    select
        series_id,
        episode_no,
        min(measured_at)                as episode_start,
        max(measured_at)                as episode_end,
        count(*)                        as breach_count,
        arg_max(z_score, abs(z_score))  as peak_z
    from numbered
    group by series_id, episode_no
)

select
    series_id,
    episode_no,
    episode_start,
    episode_end,
    breach_count,
    peak_z,
    lag(episode_end) over (partition by series_id order by episode_start) as previous_episode_end,
    coalesce(
        epoch(episode_start - previous_episode_end) < {{ var('alert_cooldown_minutes') }} * 60,
        false
    ) as is_suppressed
from episodes
