"""Module 2: Ingestor & Translator — consumes ddic_schema JSON and produces ingestor_pipeline JSON."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger

logger = get_logger()

# Priority-ordered list of standard SAP modification/creation date fields
_SAP_WATERMARK_CANDIDATES = ["AEDAT", "ERDAT", "CPUDT", "UDATE", "BUDAT", "UPDDT"]

# SAP → target type mapping sets
_STRING_TYPES = {"CLNT", "CHAR", "NUMC", "TIMS", "UNIT", "CUKY", "LANG", "ACCP"}
_DATE_TYPES = {"DATS"}
_DECIMAL_TYPES = {"CURR", "QUAN", "DEC"}
_INT_TYPES = {"INT1", "INT2", "INT4", "INT8"}


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _to_snake_case(text: str) -> str:
    """Convert a Portuguese (or any) description to lower_snake_case."""
    # Decompose accented chars and strip combining marks
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    # Replace any run of non-alphanumeric chars with a single underscore
    snaked = re.sub(r"[^a-z0-9]+", "_", lowered)
    return snaked.strip("_")


def _target_field(field_name: str, description: str) -> str:
    """Return the dbt-friendly target field name derived from the description."""
    if description:
        candidate = _to_snake_case(description)
        if candidate:
            return candidate
    return field_name.lower()


def _quote_if_needed(name: str) -> str:
    """Wrap in double quotes when the name contains non-standard SQL identifier chars (e.g. /BEV1/CAMPO)."""
    if re.search(r"[^A-Z0-9_]", name):
        return f'"{name}"'
    return name


# ---------------------------------------------------------------------------
# Type mapping & SQL expression builder
# ---------------------------------------------------------------------------

def _map_column(col: Dict[str, Any]) -> Tuple[str, str]:
    """Return (target_type, sql_expression) for a DDIC column dict.

    CAST is only emitted when a real type conversion is required.
    Text-native SAP types (CHAR, NUMC, etc.) are already NVARCHAR in HANA,
    so they are referenced directly — no CAST needed.
    """
    src = _quote_if_needed(col["field_name"].upper())
    sap_type = col["sap_type"]
    length = col["length"]
    decimals = col["decimals"]
    possivel_data = col["possivel_data"]

    # Real conversion: text-encoded date → DATE, with SAP '00000000' → NULL guard
    if possivel_data or sap_type in _DATE_TYPES:
        expr = (
            f"CASE WHEN {src} = '00000000' OR {src} = '' "
            f"THEN NULL ELSE TO_DATE({src}, 'YYYYMMDD') END"
        )
        return "DATE", expr

    # Already text in HANA (NVARCHAR/CHAR) — reference directly, no CAST
    if sap_type in _STRING_TYPES:
        return "STRING", src

    # Real conversion: numeric with scale → DECIMAL
    if sap_type in _DECIMAL_TYPES:
        return f"DECIMAL({length}, {decimals})", f"CAST({src} AS DECIMAL({length}, {decimals}))"

    # Real conversion: ABAP internal integer representation → INTEGER
    if sap_type in _INT_TYPES:
        return "INTEGER", f"CAST({src} AS INTEGER)"

    # Unknown / exotic types — reference as-is
    return "STRING", src


# ---------------------------------------------------------------------------
# Load-type & watermark logic
# ---------------------------------------------------------------------------

def _load_type(table_class: str, data_class: str, size_category: int) -> str:
    # FULL takes priority over INCREMENTAL rules
    if table_class in ("VIEW", "INTTAB") or data_class == "APPL2":
        return "FULL"
    if data_class == "APPL1" or size_category >= 3:
        return "INCREMENTAL"
    return "FULL"


def _find_watermark(ddic_columns: List[Dict[str, Any]]) -> Optional[str]:
    """Return the target_field name of the best watermark column, or None."""
    col_index = {c["field_name"].upper(): c for c in ddic_columns}

    # Priority 1: well-known SAP timestamp/change-date fields
    for candidate in _SAP_WATERMARK_CANDIDATES:
        if candidate in col_index:
            col = col_index[candidate]
            return _target_field(col["field_name"], col["field_description"])

    # Priority 2: first field flagged by the hidden-date heuristic
    for col in ddic_columns:
        if col["possivel_data"]:
            return _target_field(col["field_name"], col["field_description"])

    return None


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class IngestorTranslator:
    """Reads a ddic_schema contract and emits an ingestor_pipeline contract."""

    def __init__(self, output_dir: str = "output/contracts/pipeline") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def translate(self, ddic_contract: Dict[str, Any]) -> Dict[str, Any]:
        """Apply business rules to *ddic_contract* and return the pipeline contract."""
        table_name = ddic_contract["sap_table_name"]
        logger.info(f"[Module 2] Translating DDIC contract for: {table_name}")

        table_class = ddic_contract["table_class"]
        data_class = ddic_contract["data_class"]
        size_category = ddic_contract["size_category"]
        ddic_cols = ddic_contract["columns"]

        load = _load_type(table_class, data_class, size_category)
        logger.info(f"[Module 2] Load type resolved to: {load}")

        transformed_columns: List[Dict[str, Any]] = []
        primary_keys: List[str] = []

        for col in ddic_cols:
            # Short label (SCRTEXT_M/L) drives the column name; full DDTEXT goes to description.
            label = col.get("field_label") or col["field_description"]
            target = _target_field(col["field_name"], label)
            target_type, sql_expr = _map_column(col)

            transformed_columns.append(
                {
                    "source_field": col["field_name"],
                    "target_field": target,
                    "target_type": target_type,
                    "sql_expression": sql_expr,
                    "description": col["field_description"],
                }
            )
            if col["is_key"]:
                primary_keys.append(col["field_name"].upper())

        watermark: Optional[str] = None
        if load == "INCREMENTAL":
            watermark = _find_watermark(ddic_cols)
            if watermark:
                logger.info(f"[Module 2] Watermark column: {watermark}")
            else:
                logger.warning(f"[Module 2] No watermark column found for INCREMENTAL table {table_name}")

        contract: Dict[str, Any] = {
            "target_table": f"stg_sap_{table_name.lower()}",
            "source_sap_table": table_name,
            "table_description": ddic_contract.get("table_description", ""),
            "ingestion_strategy": {
                "load_type": load,
                "primary_keys": primary_keys,
                "watermark_column": watermark,
            },
            "transformed_columns": transformed_columns,
        }

        output_path = self.output_dir / f"ingestor_pipeline_{table_name.lower()}.json"
        output_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False))
        logger.info(f"[Module 2] Contract saved → {output_path}")

        return contract

    def translate_from_file(self, ddic_path: str) -> Dict[str, Any]:
        """Load a ddic_schema JSON from disk and run translation."""
        with open(ddic_path, encoding="utf-8") as fh:
            return self.translate(json.load(fh))
