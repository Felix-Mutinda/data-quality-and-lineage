-- What is being monitored: one row per series, identity and contract only.
-- Built from the catalogue alone; it never reads a measured value.
select
    series_id,
    resource_type,
    resource_id,
    metric,
    unit
from {{ ref('series_catalog') }}
