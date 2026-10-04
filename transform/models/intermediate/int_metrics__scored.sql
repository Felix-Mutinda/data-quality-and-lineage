-- Detector (D7): trailing z-score per series.
--   baseline = previous N readings (var detector_baseline_readings), excluding the current one
--   z        = (value - baseline_mean) / max(baseline_stddev, noise_floor)
-- No score during warm-up (fewer than N readings of history).
{{ config(materialized='table') }}

{% set n = var('detector_baseline_readings') %}

with baseline as (
    select
        series_id,
        measured_at,
        value,
        noise_floor,
        avg(value)         over w as baseline_mean,
        stddev_samp(value) over w as baseline_stddev,
        count(*)           over w as baseline_readings
    from {{ ref('int_metrics__contracted') }}
    window w as (
        partition by series_id
        order by measured_at
        rows between {{ n }} preceding and 1 preceding
    )
),

scaled as (
    select
        series_id,
        measured_at,
        value,
        baseline_mean,
        baseline_stddev,
        baseline_readings,
        greatest(coalesce(baseline_stddev, 0), coalesce(noise_floor, 0)) as score_scale
    from baseline
),

scored as (
    select
        series_id,
        measured_at,
        value,
        baseline_mean,
        baseline_stddev,
        baseline_readings,
        score_scale,
        case
            when baseline_readings >= {{ n }} and score_scale > 0
            then (value - baseline_mean) / score_scale
        end as z_score
    from scaled
)

select
    series_id,
    measured_at,
    value,
    baseline_mean,
    baseline_stddev,
    baseline_readings,
    score_scale,
    z_score,
    coalesce(abs(z_score) > {{ var('detector_z_threshold') }}, false) as is_breach
from scored
