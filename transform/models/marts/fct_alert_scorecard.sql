-- Alert quality per series against NAB's labelled windows (D3):
-- how often the series pages, how many pages land in a real incident,
-- and how many labelled incidents got at least one page.
with spans as (
    select series_id, epoch(max(measured_at) - min(measured_at)) / 86400.0 as days_observed
    from {{ ref('stg_nab__metrics') }}
    group by series_id
),

windows as (
    select *, row_number() over (partition by series_id order by window_start) as window_no
    from {{ ref('stg_nab__anomaly_windows') }}
),

page_hits as (
    select
        a.alert_id,
        a.series_id,
        min(w.window_no) as window_no
    from {{ ref('fct_alerts') }} as a
    left join windows as w
      on w.series_id = a.series_id
     and a.alerted_at between w.window_start and w.window_end
    group by a.alert_id, a.series_id
)

select
    s.series_id,
    round(s.days_observed, 1)                                               as days_observed,
    count(distinct p.alert_id)                                              as pages,
    round(count(distinct p.alert_id) / s.days_observed, 2)                  as pages_per_day,
    count(distinct p.alert_id) filter (where p.window_no is not null)       as pages_in_labelled_window,
    (select count(*) from windows w where w.series_id = s.series_id)        as labelled_windows,
    count(distinct p.window_no)                                             as labelled_windows_paged
from spans as s
left join page_hits as p using (series_id)
group by s.series_id, s.days_observed
