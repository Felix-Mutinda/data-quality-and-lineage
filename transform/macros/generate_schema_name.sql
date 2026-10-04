{#- Use configured schema names as-is (staging, reference, marts, ...) instead of
    dbt's default "<target_schema>_<schema>". Keeps names readable everywhere
    they appear: queries, test output, and later the lineage graph. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name is not none else target.schema }}
{%- endmacro %}
