"""Module 3: dbt Artifact Generator — writes stg_[table].sql and schema.yml from a pipeline contract."""

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

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
    watermark = strategy.get("watermark_column")
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
            "        incremental_strategy='merge'",
            f"        alias='{source_table.lower()}'",
            f"        tags=['sap','datasphere','silver', '{source_table}']",
            f"        unique_key={pk_str},",
            f"        indexes=[{{'columns': {pk_str}, 'type': 'btree'}}],",
            "    )",
            "}}",
            "{% if is_incremental() %}",
            "    WITH novos_hashes AS (",
            "        SELECT s_tgt.hash_pk",
            f"        FROM {{ source('dataspherev2', '{source_table.lower()}') }} AS s_tgt",
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
            "        materialized='table'",
            f"        alias='{source_table.lower()}'",
            f"        tags=['sap','datasphere','silver', '{source_table}']",
            f"        unique_key={pk_str},",
            f"        indexes=[{{'columns': {pk_str}, 'type': 'btree'}}],",
            "    )",
            "}}",
        ]

    lines.append("")

    # --- SELECT ---
    lines.append("SELECT")
    col_lines = [f"    {col['sql_expression']} AS {col['target_field']}" for col in columns]
    lines.append(",\n".join(col_lines))
    lines.append(f"FROM {{{{ source('{source_name}', '{source_table}') }}}}")

    # --- incremental filter ---
    if load_type == "INCREMENTAL" and watermark:
        lines += [
            "{%- if is_incremental() %}",
            f"WHERE {watermark} > (SELECT MAX({watermark}) FROM {{{{ this }}}})",
            "{%- endif %}",
        ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# YAML builder
# ---------------------------------------------------------------------------

def _build_model_entry(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    """Return a dict representing one model entry for schema.yml."""
    target_table = pipeline["target_table"]
    table_description = pipeline.get("table_description", "")
    strategy = pipeline["ingestion_strategy"]
    columns = pipeline["transformed_columns"]

    # primary_keys stores technical names (mandt, matnr); resolve to target_fields for YAML tests
    col_map = _source_to_target_map(columns)
    pk_target_set = set(_resolve_pk_targets(strategy.get("primary_keys", []), col_map))

    col_entries = []
    for col in columns:
        entry: Dict[str, Any] = {
            "name": col["target_field"],
        }
        if col.get("description"):
            entry["description"] = col["description"]
        if col["target_field"] in pk_target_set:
            entry["tests"] = ["unique", "not_null"]
        col_entries.append(entry)

    return {
        "name": target_table,
        "description": table_description,
        "columns": col_entries,
    }


def _load_schema_yml(path: Path) -> Dict[str, Any]:
    """Load existing schema.yml or return a blank structure."""
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if "models" not in data:
            data["models"] = []
        return data
    return {"version": 2, "models": []}


def _save_schema_yml(path: Path, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class DbtGenerator:
    """Reads a pipeline contract and writes stg_*.sql + schema.yml dbt artifacts."""

    def __init__(
        self,
        output_dir: str = "output/dbt/models/staging",
        source_name: str = "sap",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.source_name = source_name

    def generate(self, pipeline_contract: Dict[str, Any]) -> None:
        """Write SQL model and update schema.yml for the given pipeline contract."""
        target_table = pipeline_contract["target_table"]
        source_table = pipeline_contract["source_sap_table"]
        logger.info(f"[Module 3] Generating dbt artifacts for: {target_table}")

        # --- SQL model ---
        sql_content = _build_sql(pipeline_contract, self.source_name)
        sql_path = self.output_dir / source_table / f"{target_table}.sql"
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(sql_content, encoding="utf-8")
        logger.info(f"[Module 3] SQL model saved → {sql_path}")

        # --- schema.yml (merge or create) ---
        yml_path = self.output_dir / source_table / f"{target_table}.yml"
        yml_path.parent.mkdir(parents=True, exist_ok=True)
        schema = _load_schema_yml(yml_path)

        # Replace existing entry for this model if present, otherwise append
        model_entry = _build_model_entry(pipeline_contract)
        existing_names = [m.get("name") for m in schema["models"]]
        if target_table in existing_names:
            idx = existing_names.index(target_table)
            schema["models"][idx] = model_entry
            logger.info(f"[Module 3] schema.yml: updated existing entry for {target_table}")
        else:
            schema["models"].append(model_entry)
            logger.info(f"[Module 3] schema.yml: added new entry for {target_table}")

        _save_schema_yml(yml_path, schema)
        logger.info(f"[Module 3] schema.yml saved → {yml_path}")

    def generate_from_file(self, pipeline_path: str) -> None:
        """Load a pipeline contract JSON from disk and generate dbt artifacts."""
        with open(pipeline_path, encoding="utf-8") as fh:
            self.generate(json.load(fh))
