"""SQL queries for extracting SAP DDIC metadata via Datasphere."""

# Table-level metadata: joins DD02L (table header), DD02T (description), DD09L (technical settings).
_TABLE_META = """
SELECT
    t.TABNAME                  AS sap_table_name,
    COALESCE(tx.DDTEXT, '')    AS table_description,
    t.TABCLASS                 AS table_class,
    COALESCE(ts.TABART, '')    AS data_class,
    COALESCE(ts.TABKAT, '0')   AS size_category
FROM {ddic_schema}.DD02L t
LEFT JOIN {ddic_schema}.DD02T tx
    ON  t.TABNAME     = tx.TABNAME
    AND tx.DDLANGUAGE = :language
    AND tx.AS4LOCAL   = 'A'
LEFT JOIN {ddic_schema}.DD09L ts
    ON  t.TABNAME   = ts.TABNAME
    AND ts.AS4LOCAL = 'A'
WHERE t.TABNAME  = :table_name
  AND t.AS4LOCAL = 'A'
"""

# Field-level metadata: joins DD03L (fields), DD04T (data element descriptions).
# Excludes structural include markers (FIELDNAME NOT LIKE '.%').
_COLUMNS = """
SELECT
    f.FIELDNAME             AS field_name,
    f.POSITION              AS position,
    f.KEYFLAG               AS keyflag,
    f.DATATYPE              AS sap_type,
    f.LENG                  AS length,
    f.DECIMALS              AS decimals,
    f.ROLLNAME              AS data_element,
    COALESCE(f.DOMNAME, '') AS domain_name,
    COALESCE(et.DDTEXT, '')    AS field_description,
    COALESCE(et.SCRTEXT_M, '') AS field_label_m,
    COALESCE(et.SCRTEXT_L, '') AS field_label_l
FROM {ddic_schema}.DD03L f
LEFT JOIN {ddic_schema}.DD04T et
    ON  f.ROLLNAME    = et.ROLLNAME
    AND et.DDLANGUAGE = :language
    AND et.AS4LOCAL   = 'A'
WHERE f.TABNAME  = :table_name
  AND f.AS4LOCAL = 'A'
  AND f.FIELDNAME NOT LIKE '.%'
ORDER BY CAST(f.POSITION AS INTEGER)
"""


def table_metadata_query(ddic_schema: str) -> str:
    return _TABLE_META.format(ddic_schema=ddic_schema)


def columns_query(ddic_schema: str) -> str:
    return _COLUMNS.format(ddic_schema=ddic_schema)
