-- Macros utilitárias para tratamento de dados do Datasphere

{% macro nullif_empty(column_name) %}
    NULLIF({{ column_name }}, '')
{% endmacro %}

{% macro to_decimal(column_name, precision=18, scale=6) %}
    TRY_CAST(REPLACE(REPLACE({{ column_name }}, ',', '.'), ' ', '') AS DECIMAL({{ precision }}, {{ scale }}))
{% endmacro %}

{% macro to_integer(column_name) %}
    TRY_CAST(REPLACE(REPLACE({{ column_name }}, ',', '.'), ' ', '') AS INTEGER)
{% endmacro %}

{% macro to_date(column_name) %}
    TRY_CONVERT(DATE, {{ column_name }})
{% endmacro %}

{% macro to_timestamp(column_name) %}
    TRY_CONVERT(DATETIME2, {{ column_name }})
{% endmacro %}

{% macro to_bigint(column_name) %}
    TRY_CAST(REPLACE(REPLACE({{ column_name }}, ',', '.'), ' ', '') AS BIGINT)
{% endmacro %}

-- Macros combinadas: NULLIF + conversão de tipo
{% macro to_integer_nullif(column_name) %}
    TRY_CAST(REPLACE(REPLACE(NULLIF({{ column_name }}, ''), ',', '.'), ' ', '') AS INTEGER)
{% endmacro %}

{% macro to_bigint_nullif(column_name) %}
    TRY_CAST(REPLACE(REPLACE(NULLIF({{ column_name }}, ''), ',', '.'), ' ', '') AS BIGINT)
{% endmacro %}

{% macro to_decimal_nullif(column_name, precision=18, scale=6) %}
    TRY_CAST(REPLACE(REPLACE(NULLIF({{ column_name }}, ''), ',', '.'), ' ', '') AS DECIMAL({{ precision }}, {{ scale }}))
{% endmacro %}
