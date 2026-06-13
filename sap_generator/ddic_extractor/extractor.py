"""Module 1: DDIC Extractor — queries SAP DDIC tables and produces ddic_schema_[table].json."""

import json
from pathlib import Path
from typing import Any, Dict

from datasphere.datasphere_extractor import DatasphereExtractor
from logger import get_logger

from .queries import columns_query, table_metadata_query

logger = get_logger()

# SAP types that could encode dates as text strings
_DATE_CANDIDATE_TYPES = {"CHAR", "NUMC"}

# Keywords that signal a hidden date field in the element name, domain, or description
_DATE_KEYWORDS = {"DATA", "DT", "DATUM", "TIMESTAMP", "CRIADO", "MODIFICADO", "DATE"}


def _is_hidden_date(sap_type: str, length: int, data_element: str, domain_name: str, description: str) -> bool:
    """Return True if a CHAR/NUMC field (8–10 chars) appears to encode a date."""
    if sap_type not in _DATE_CANDIDATE_TYPES:
        return False
    if not (8 <= length <= 10):
        return False
    combined = f"{data_element} {domain_name} {description}".upper()
    return any(kw in combined for kw in _DATE_KEYWORDS)


class DDICExtractor:
    """Queries SAP DDIC metadata via Datasphere and emits ddic_schema_[table].json."""

    def __init__(
        self,
        extractor: DatasphereExtractor,
        ddic_schema: str,
        language: str = "P",
        output_dir: str = "output/contracts/ddic",
    ) -> None:
        self.extractor = extractor
        self.ddic_schema = ddic_schema
        self.language = language
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, table_name: str) -> Dict[str, Any]:
        """Extract DDIC metadata for *table_name* and save contract to disk.

        Returns the contract dict so callers can pipe it directly to Module 2.
        """
        logger.info(f"[Module 1] Extracting DDIC schema for table: {table_name}")

        meta_df = self.extractor.execute_query_to_df(
            table_metadata_query(self.ddic_schema),
            params={"table_name": table_name, "language": self.language},
        )
        if meta_df.empty:
            raise ValueError(f"Table '{table_name}' not found in DDIC (schema: {self.ddic_schema})")

        row = meta_df.iloc[0]

        cols_df = self.extractor.execute_query_to_df(
            columns_query(self.ddic_schema),
            params={"table_name": table_name, "language": self.language},
        )

        columns = []
        for _, col in cols_df.iterrows():
            sap_type = str(col["sap_type"] or "").strip()
            length = int(str(col["length"] or "0").strip() or 0)
            decimals = int(str(col["decimals"] or "0").strip() or 0)
            data_element = str(col["data_element"] or "").strip()
            domain_name = str(col["domain_name"] or "").strip()
            field_description = str(col["field_description"] or "").strip()
            # Prefer the shorter screen texts (SCRTEXT_M ~20 chars, then SCRTEXT_L ~40 chars)
            # over the full DDTEXT for generating concise column names and YAML descriptions.
            field_label = (
                str(col.get("field_label_m") or "").strip()
                or str(col.get("field_label_l") or "").strip()
                or field_description
            )

            columns.append(
                {
                    "field_name": str(col["field_name"]).strip(),
                    "position": int(str(col["position"] or "0").strip() or 0),
                    "is_key": str(col["keyflag"]).strip() == "X",
                    "sap_type": sap_type,
                    "length": length,
                    "decimals": decimals,
                    "data_element": data_element,
                    "field_description": field_description,
                    "field_label": field_label,
                    "possivel_data": _is_hidden_date(
                        sap_type, length, data_element, domain_name, field_description
                    ),
                }
            )

        contract: Dict[str, Any] = {
            "sap_table_name": str(row["sap_table_name"]).strip(),
            "table_description": str(row["table_description"]).strip(),
            "table_class": str(row["table_class"]).strip(),
            "data_class": str(row["data_class"]).strip(),
            "size_category": int(str(row["size_category"]).strip() or 0),
            "columns": columns,
        }

        output_path = self.output_dir / f"ddic_schema_{table_name.lower()}.json"
        output_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False))
        logger.info(f"[Module 1] Contract saved → {output_path}")

        return contract

    def extract_from_file(self, table_name: str, path: str) -> Dict[str, Any]:
        """Load an existing ddic_schema JSON from disk instead of querying SAP."""
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
