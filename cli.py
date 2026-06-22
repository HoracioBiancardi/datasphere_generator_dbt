"""CLI — ponto de entrada via Typer (independente de main.py).

Uso:
    uv run cli.py run      MARA BSEG VBAK
    uv run cli.py ddic     MARA BSEG
    uv run cli.py translate MARA [--from-file FILE] [--ddic-dir DIR]
    uv run cli.py generate  MARA [--from-file FILE] [--pipeline-dir DIR]
"""

import os
from typing import List, Optional

import typer
from datasphere.datasphere_extractor import DatasphereConnector, DatasphereExtractor
from dotenv import load_dotenv

from logger import get_logger
from sap_generator.ddic_extractor import DDICExtractor
from sap_generator.dbt_generator import DbtGenerator
from sap_generator.ingestor import IngestorTranslator

load_dotenv()
logger = get_logger()

# ── Variáveis de ambiente ─────────────────────────────────────────────────────
HANA_ADDRESS  = os.environ["HANA_ADDRESS"]
HANA_PORT     = int(os.environ["HANA_PORT"])
HANA_USER     = os.environ["HANA_USER"]
HANA_PASSWORD = os.environ["HANA_PASSWORD"]
HANA_SCHEMA   = os.getenv("HANA_SCHEMA")

DDIC_SCHEMA   = os.environ["DDIC_SCHEMA"]
DDIC_LANGUAGE = os.getenv("DDIC_LANGUAGE", "P")

DBT_SOURCE_NAME = os.getenv("DBT_SOURCE_NAME", "dataspherev2")
DBT_DATABASE    = os.getenv("DBT_DATABASE", "BRONZE")
DBT_SCHEMA      = os.getenv("DBT_SCHEMA", "dataspherev2")


# ── Builders ──────────────────────────────────────────────────────────────────

def _connector() -> DatasphereConnector:
    config: dict = {
        "host": HANA_ADDRESS,
        "port": HANA_PORT,
        "user": HANA_USER,
        "password": HANA_PASSWORD,
    }
    if HANA_SCHEMA:
        config["schema"] = HANA_SCHEMA
    return DatasphereConnector(config=config)


def _ddic_extractor(output_dir: str) -> DDICExtractor:
    return DDICExtractor(
        extractor=DatasphereExtractor(connector=_connector()),
        ddic_schema=DDIC_SCHEMA,
        language=DDIC_LANGUAGE,
        output_dir=output_dir,
    )


def _translator(output_dir: str) -> IngestorTranslator:
    return IngestorTranslator(output_dir=output_dir)


def _generator(output_dir: str) -> DbtGenerator:
    return DbtGenerator(
        output_dir=output_dir,
        source_name=DBT_SOURCE_NAME,
        database=DBT_DATABASE,
        schema=DBT_SCHEMA,
    )


# ── App ───────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="datasphere-dbt",
    help="SAP Datasphere → dbt staging model generator.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ── Comandos ──────────────────────────────────────────────────────────────────

@app.command("run")
def cmd_run(
    tables: List[str] = typer.Argument(..., help="Nome(s) da tabela SAP. Ex: MARA BSEG VBAK"),
) -> None:
    """Executa o pipeline completo: DDIC → tradução → geração dbt."""
    ddic_ext   = _ddic_extractor("output/contracts/ddic")
    translator = _translator("output/contracts/pipeline")
    generator  = _generator("output/dbt/models/staging")

    failed = []
    for table in tables:
        table = table.upper()
        try:
            logger.info(f"=== {table} ===")
            ddic     = ddic_ext.extract(table)
            pipeline = translator.translate(ddic)
            generator.generate(pipeline)
        except Exception as exc:
            logger.error(f"[run] {table} — {exc}")
            failed.append(table)

    if failed:
        logger.error(f"Falhou: {', '.join(failed)}")
        raise typer.Exit(1)


@app.command("ddic")
def cmd_ddic(
    tables: List[str] = typer.Argument(..., help="Nome(s) da tabela SAP."),
    output_dir: str = typer.Option("output/contracts/ddic", metavar="DIR",
                                   help="Destino dos contratos DDIC."),
) -> None:
    """Extrai metadados DDIC do SAP (Módulo 1) e salva ddic_schema_<TABLE>.json."""
    extractor = _ddic_extractor(output_dir)
    failed = []
    for table in tables:
        try:
            extractor.extract(table.upper())
        except Exception as exc:
            logger.error(f"[ddic] {table.upper()} — {exc}")
            failed.append(table)
    if failed:
        raise typer.Exit(1)


@app.command("translate")
def cmd_translate(
    tables: Optional[List[str]] = typer.Argument(None, help="Nome(s) da tabela SAP."),
    from_file: Optional[List[str]] = typer.Option(None, "--from-file", metavar="FILE",
                                                   help="Caminho direto para um ddic_schema JSON (repetível)."),
    ddic_dir: str = typer.Option("output/contracts/ddic", metavar="DIR",
                                 help="Diretório com os contratos DDIC."),
    output_dir: str = typer.Option("output/contracts/pipeline", metavar="DIR",
                                   help="Destino dos contratos de pipeline."),
) -> None:
    """Mapeia tipos SAP e define estratégia de carga (Módulo 2)."""
    if not tables and not from_file:
        logger.error("Informe ao menos uma TABLE ou --from-file.")
        raise typer.Exit(1)

    translator = _translator(output_dir)
    failed = []

    for table in tables or []:
        path  = os.path.join(ddic_dir, f"ddic_schema_{table.lower()}.json")
        label = table.upper()
        if not os.path.exists(path):
            logger.error(f"[translate] {label} — arquivo não encontrado: {path}")
            failed.append(label)
            continue
        try:
            translator.translate_from_file(path)
        except Exception as exc:
            logger.error(f"[translate] {label} — {exc}")
            failed.append(label)

    for file_path in from_file or []:
        label = os.path.basename(file_path)
        try:
            translator.translate_from_file(file_path)
        except Exception as exc:
            logger.error(f"[translate] {label} — {exc}")
            failed.append(label)

    if failed:
        raise typer.Exit(1)


@app.command("generate")
def cmd_generate(
    tables: Optional[List[str]] = typer.Argument(None, help="Nome(s) da tabela SAP."),
    from_file: Optional[List[str]] = typer.Option(None, "--from-file", metavar="FILE",
                                                   help="Caminho direto para um pipeline contract JSON (repetível)."),
    pipeline_dir: str = typer.Option("output/contracts/pipeline", metavar="DIR",
                                     help="Diretório com os contratos de pipeline."),
    output_dir: str = typer.Option("output/dbt/models/staging", metavar="DIR",
                                   help="Destino dos artefatos dbt."),
) -> None:
    """Gera stg_sap_<TABLE>.sql e sources.yml para dbt (Módulo 3)."""
    if not tables and not from_file:
        logger.error("Informe ao menos uma TABLE ou --from-file.")
        raise typer.Exit(1)

    generator = _generator(output_dir)
    failed = []

    for table in tables or []:
        path  = os.path.join(pipeline_dir, f"ingestor_pipeline_{table.lower()}.json")
        label = table.upper()
        if not os.path.exists(path):
            logger.error(f"[generate] {label} — arquivo não encontrado: {path}")
            failed.append(label)
            continue
        try:
            generator.generate_from_file(path)
        except Exception as exc:
            logger.error(f"[generate] {label} — {exc}")
            failed.append(label)

    for file_path in from_file or []:
        label = os.path.basename(file_path)
        try:
            generator.generate_from_file(file_path)
        except Exception as exc:
            logger.error(f"[generate] {label} — {exc}")
            failed.append(label)

    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
