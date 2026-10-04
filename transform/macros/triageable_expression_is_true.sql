{#-
  Make dbt-expectations failures traceable to rows.

  dbt_expectations' row-level tests compile down to expression_is_true, which
  stores one boolean per failing row. With store_failures on, a warning on the
  stuck-agent test saves 122 rows of `false`: no series, no timestamp, nothing
  to triage from.

  dbt_expectations dispatches this macro, so the project overrides it (see the
  `dispatch` block in dbt_project.yml) to keep every column of the failing row.
  Grouped tests (group_by_columns) keep the package behaviour.
-#}
{% macro default__expression_is_true(model, expression, test_condition, group_by_columns, row_condition) -%}
{%- if group_by_columns -%}
    {{ dbt_expectations.default__expression_is_true(model, expression, test_condition, group_by_columns, row_condition) }}
{%- else -%}
with checked as (
    select
        *,
        {{ dbt_expectations.truth_expression(expression) }}
    from {{ model }}
    {%- if row_condition %}
    where {{ row_condition }}
    {%- endif %}
)
select *
from checked
where not(expression {{ test_condition }})
{%- endif -%}
{%- endmacro %}
