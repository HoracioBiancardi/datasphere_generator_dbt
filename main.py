"""Orchestrator: runs the three-module SAP → dbt pipeline for one or more tables."""

import argparse
import os

from datasphere.datasphere_extractor import DatasphereConnector, DatasphereExtractor
from dotenv import load_dotenv

from logger import get_logger
from sap_generator.ddic_extractor import DDICExtractor
from sap_generator.dbt_generator import DbtGenerator
from sap_generator.ingestor import IngestorTranslator

load_dotenv()
logger = get_logger()


def _build_connector() -> DatasphereConnector:
    config = {
        "host": os.environ["HANA_ADDRESS"],
        "port": int(os.environ["HANA_PORT"]),
        "user": os.environ["HANA_USER"],
        "password": os.environ["HANA_PASSWORD"],
    }
    schema = os.getenv("HANA_SCHEMA")
    if schema:
        config["schema"] = schema
    return DatasphereConnector(config=config)


def run_pipeline(table_name: str) -> None:
    """Execute Modules 1 → 2 → 3 for *table_name*."""
    logger.info(f"=== Starting SAP → dbt pipeline for: {table_name} ===")

    ddic_schema = os.environ["DDIC_SCHEMA"]
    language = os.getenv("DDIC_LANGUAGE", "P")
    dbt_source = os.getenv("DBT_SOURCE_NAME", "dataspherev2")
    dbt_database = os.getenv("DBT_DATABASE", "BRONZE")
    dbt_schema = os.getenv("DBT_SCHEMA", "dataspherev2")

    connector = _build_connector()
    raw_extractor = DatasphereExtractor(connector=connector)

    # Module 1 — DDIC extraction
    ddic_extractor = DDICExtractor(
        extractor=raw_extractor,
        ddic_schema=ddic_schema,
        language=language,
        output_dir="output/contracts/ddic",
    )
    ddic_contract = ddic_extractor.extract(table_name)

    # Module 2 — type mapping & ingestion strategy
    translator = IngestorTranslator(output_dir="output/contracts/pipeline")
    pipeline_contract = translator.translate(ddic_contract)

    # Module 3 — dbt artifact generation
    generator = DbtGenerator(
        output_dir="output/dbt/models/staging",
        source_name=dbt_source,
        database=dbt_database,
        schema=dbt_schema,
    )
    generator.generate(pipeline_contract)

    logger.info(f"=== Pipeline complete for: {table_name} ===")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate dbt staging models from SAP DDIC metadata."
    )
    parser.add_argument(
        "tables",
        nargs="+",
        metavar="TABLE",
        help="One or more SAP table names (e.g. MARA BSEG VBAK)",
    )
    args = parser.parse_args()

    for table in args.tables:
        run_pipeline(table.upper())


if __name__ == "__main__":
    main()
