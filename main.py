"""Configurações, variáveis de ambiente e funções do pipeline SAP → dbt."""

import os

from datasphere.datasphere_extractor import DatasphereConnector, DatasphereExtractor
from dotenv import load_dotenv

from logger import get_logger
from sap_generator.ddic_extractor import DDICExtractor
from sap_generator.dbt_generator import DbtGenerator
from sap_generator.ingestor import IngestorTranslator

load_dotenv()
logger = get_logger()

# ── Conexão HANA ──────────────────────────────────────────────────────────────
HANA_ADDRESS  = os.environ["HANA_ADDRESS"]
HANA_PORT     = int(os.environ["HANA_PORT"])
HANA_USER     = os.environ["HANA_USER"]
HANA_PASSWORD = os.environ["HANA_PASSWORD"]
HANA_SCHEMA   = os.getenv("HANA_SCHEMA")

# ── Módulo 1 ──────────────────────────────────────────────────────────────────
DDIC_SCHEMA   = os.environ["DDIC_SCHEMA"]
DDIC_LANGUAGE = os.getenv("DDIC_LANGUAGE", "P")
DDIC_OUTPUT   = "output/contracts/ddic"

# ── Módulo 2 ──────────────────────────────────────────────────────────────────
PIPELINE_OUTPUT = "output/contracts/pipeline"

# ── Módulo 3 ──────────────────────────────────────────────────────────────────
DBT_SOURCE_NAME = os.getenv("DBT_SOURCE_NAME", "dataspherev2")
DBT_DATABASE    = os.getenv("DBT_DATABASE", "BRONZE")
DBT_SCHEMA      = os.getenv("DBT_SCHEMA", "dataspherev2")
DBT_OUTPUT      = "output/dbt/models/staging"


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_connector() -> DatasphereConnector:
    config: dict = {
        "host": HANA_ADDRESS,
        "port": HANA_PORT,
        "user": HANA_USER,
        "password": HANA_PASSWORD,
    }
    if HANA_SCHEMA:
        config["schema"] = HANA_SCHEMA
    return DatasphereConnector(config=config)


def build_ddic_extractor(output_dir: str = DDIC_OUTPUT) -> DDICExtractor:
    return DDICExtractor(
        extractor=DatasphereExtractor(connector=build_connector()),
        ddic_schema=DDIC_SCHEMA,
        language=DDIC_LANGUAGE,
        output_dir=output_dir,
    )


def build_translator(output_dir: str = PIPELINE_OUTPUT) -> IngestorTranslator:
    return IngestorTranslator(output_dir=output_dir)


def build_generator(output_dir: str = DBT_OUTPUT) -> DbtGenerator:
    return DbtGenerator(
        output_dir=output_dir,
        source_name=DBT_SOURCE_NAME,
        database=DBT_DATABASE,
        schema=DBT_SCHEMA,
    )


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(table_name: str) -> None:
    """Executa os três módulos em sequência para uma tabela SAP."""
    table_name = table_name.upper()
    logger.info(f"=== {table_name} ===")

    ddic_contract     = build_ddic_extractor().extract(table_name)
    pipeline_contract = build_translator().translate(ddic_contract)
    build_generator().generate(pipeline_contract)

    logger.info(f"=== Pipeline completo: {table_name} ===")


# ── Entry point direto (sem CLI) ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if not sys.argv[1:]:
        logger.warning("Uso: uv run main.py TABLE [TABLE ...]")
        logger.warning("Ex:  uv run main.py MARA BSEG VBAK")
        sys.exit(0)

    for table in sys.argv[1:]:
        run_pipeline(table)
