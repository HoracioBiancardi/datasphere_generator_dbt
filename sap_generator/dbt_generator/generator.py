"""Module 3: dbt Artifact Generator — writes stg_[table].sql and sources.yml from a pipeline contract."""

import json
from pathlib import Path
from typing import Any, Dict, List

from logger import get_logger

logger = get_logger()


# ---------------------------------------------------------------------------
# SQL builder
# ---------------------------------------------------------------------------

def _pk_literal(primary_keys: List[str]) -> str:
    """Render primary_keys as a Jinja-safe Python literal for dbt config."""
    if len(primary_keys) == 1:
        return f"'{primary_keys[0]}'"
    keys = ", ".join(f"'{k}'" for k in primary_keys)
    return f"[{keys}]"


def _source_to_target_map(columns: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map lowercase technical source field names to their dbt target field names."""
    return {col["source_field"].lower(): col["target_field"] for col in columns}


def _resolve_pk_targets(primary_keys: List[str], col_map: Dict[str, str]) -> List[str]:
    """Translate technical primary key names to their target_field equivalents."""
    return [col_map.get(pk, pk) for pk in primary_keys]


def _build_sql(pipeline: Dict[str, Any], source_name: str) -> str:
    strategy = pipeline["ingestion_strategy"]
    load_type = strategy["load_type"]
    primary_keys = strategy["primary_keys"]
    source_table = pipeline["source_sap_table"]
    columns = pipeline["transformed_columns"]

    col_map = _source_to_target_map(columns)
    pk_targets = _resolve_pk_targets(primary_keys, col_map)

    lines: List[str] = []

    # --- config block ---
    if load_type == "INCREMENTAL":
        pk_str = _pk_literal(pk_targets)
        lines += [
            "{{",
            "    config(",
            "        materialized='incremental',",
            "        incremental_strategy='delete+insert',",
            f"        alias='{source_table.lower()}',",
            f"        tags=['sap','datasphere','silver', '{source_table}'],",
            f"        unique_key='hash_pk',",
            "    )",
            "}}",
            "{% if is_incremental() %}",
            "    WITH novos_hashes AS (",
            "        SELECT s_tgt.hash_pk",
            f"        FROM {{{{ source('{source_name}', '{source_table.lower()}') }}}} AS s_tgt",
            "        WHERE TRY_CONVERT(DATETIME2, s_tgt.dt_ingestao) >= (",
            "                SELECT DATEADD(",
            "                    DAY, -1, MAX(s_src.dt_ingestao)",
            "                ) FROM {{ this }} AS s_src",
            "            )",
            "    )",
            "{% endif %}",
        ]
    else:
        pk_str = _pk_literal(pk_targets)
        lines += [
            "{{",
            "    config(",
            "        materialized='table',",
            f"        alias='{source_table.lower()}',",
            f"        tags=['sap','datasphere','silver', '{source_table}'],",
            f"        unique_key='hash_pk',",
            "    )",
            "}}",
        ]

    lines.append("")

    # --- SELECT ---
    lines.append("SELECT")
    col_lines = [f"    {col['sql_expression']} AS {col['target_field']}" for col in columns]

    if load_type == "INCREMENTAL":
        audit_block = (
            ",\n"
            "    -- Metadados de Auditoria da Pipeline\n"
            "    {{ to_timestamp('dt_ingestao') }} AS dt_ingestao,\n"
            "    silver.hash_pk,\n"
            "    silver.source"
        )
        lines.append(",\n".join(col_lines) + audit_block)
        lines += [
            f"FROM {{{{ source('{source_name}', '{source_table.lower()}') }}}} AS silver",
            "    {% if is_incremental() %}",
            "        INNER JOIN novos_hashes AS nhashes ON silver.hash_pk = nhashes.hash_pk",
            "    {% endif %}",
        ]
    else:
        lines.append(",\n".join(col_lines))
        lines.append(f"FROM {{{{ source('{source_name}', '{source_table.lower()}') }}}}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# YAML builder (sources format)
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    """Escape a string for a double-quoted YAML scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_sources_yml(
    pipeline: Dict[str, Any],
    source_name: str,
    database: str,
    schema: str,
) -> str:
    """Render a dbt sources YAML string with PK section comments."""
    source_table = pipeline["source_sap_table"].lower()
    table_description = _esc(pipeline.get("table_description", ""))
    strategy = pipeline["ingestion_strategy"]
    load_type = strategy["load_type"]
    columns = pipeline["transformed_columns"]

    col_map = _source_to_target_map(columns)
    pk_target_set = set(_resolve_pk_targets(strategy.get("primary_keys", []), col_map))

    materialized = "incremental" if load_type == "INCREMENTAL" else "table"

    out: List[str] = [
        "sources:",
        f"  - name: {source_name}",
        f"    database: {database}",
        f"    schema: {schema}",
        "    tables:",
        f"      - name: {source_table}",
        f'        description: "{table_description}"',
        "        config:",
        f"          materialized: {materialized}",
    ]

    if load_type == "INCREMENTAL":
        out.append('          incremental_strategy: "delete+insert"')
    out.append('          unique_key: "hash_pk"')
    out.append(f'          tags: ["{source_name}", "silver"]')
    out.append("")
    out.append("        columns:")

    pk_cols = [c for c in columns if c["target_field"] in pk_target_set]
    non_pk_cols = [c for c in columns if c["target_field"] not in pk_target_set]

    if pk_cols:
        out.append("          # Chaves Primárias / Identificadores")
        for col in pk_cols:
            out.append(f"          - name: {col['target_field']}")
            desc = _esc(col.get("description") or "")
            if desc:
                out.append(f'            description: "{desc}"')

    for col in non_pk_cols:
        out.append(f"          - name: {col['target_field']}")
        desc = _esc(col.get("description") or "")
        if desc:
            out.append(f'            description: "{desc}"')

    out += [
        "",
        "          # Metadados de Auditoria da Pipeline",
        '          - name: hash_pk',
        '            description: "Chave primária MD5 gerada artificialmente para identificação única do registro"',
        '          - name: dt_ingestao',
        '            description: "Data e hora da ingestão na bronze"',
        '          - name: source',
        '            description: "Identificador da fonte dos dados"',
    ]

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class DbtGenerator:
    """Reads a pipeline contract and writes stg_*.sql + sources.yml dbt artifacts."""

    def __init__(
        self,
        output_dir: str = "output/dbt/models/staging",
        source_name: str = "dataspherev2",
        database: str = "BRONZE",
        schema: str = "dataspherev2",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.source_name = source_name
        self.database = database
        self.schema = schema

    def generate(self, pipeline_contract: Dict[str, Any]) -> None:
        """Write SQL model and sources.yml for the given pipeline contract."""
        source_table = pipeline_contract["source_sap_table"]
        table_name = source_table.lower()
        logger.info(f"[Module 3] Generating dbt artifacts for: {table_name}")

        # --- SQL model ---
        sql_content = _build_sql(pipeline_contract, self.source_name)
        sql_path = self.output_dir / table_name / f"{table_name}.sql"
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(sql_content, encoding="utf-8")
        logger.info(f"[Module 3] SQL model saved → {sql_path}")

        # --- sources.yml ---
        yml_content = _build_sources_yml(
            pipeline_contract, self.source_name, self.database, self.schema
        )
        yml_path = self.output_dir / table_name / f"{table_name}.yml"
        yml_path.parent.mkdir(parents=True, exist_ok=True)
        yml_path.write_text(yml_content, encoding="utf-8")
        logger.info(f"[Module 3] sources.yml saved → {yml_path}")

    def generate_from_file(self, pipeline_path: str) -> None:
        """Load a pipeline contract JSON from disk and generate dbt artifacts."""
        with open(pipeline_path, encoding="utf-8") as fh:
            self.generate(json.load(fh))
