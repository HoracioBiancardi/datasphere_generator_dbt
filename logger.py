"""Configuração de logging com Rich, arquivo e JSON."""

import contextlib
import json
import logging
import logging.handlers
from collections.abc import Hashable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import rich.box
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.theme import Theme

_THEME = Theme(
    {
        "logging.level.debug": "dim cyan",
        "logging.level.info": "bold green",
        "logging.level.warning": "bold yellow",
        "logging.level.error": "bold red",
        "logging.level.critical": "bold white on red",
    }
)

_console = Console(theme=_THEME)

_FILE_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)



class _JsonFormatter(logging.Formatter):
    """Formata cada record como uma linha JSON — compatível com Airflow e log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(
    name: str = "app",
    level: int = logging.INFO,
    log_file: str | Path | None = None,
    json_format: bool = False,
) -> logging.Logger:
    """Retorna um logger nomeado com formatação Rich, arquivo e/ou JSON.

    Cria os handlers apenas uma vez por logger, evitando duplicatas em
    chamadas subsequentes.

    Args:
        name: Nome do logger. Use __name__ para identificar o módulo chamador.
        level: Nível de logging (logging.DEBUG, INFO, WARNING, etc.).
        log_file: Caminho para arquivo de log com rotação automática (10 MB / 5 backups).
                  None desativa o log em arquivo.
        json_format: Se True, emite JSON no stdout em vez de Rich — ideal para Airflow
                     e sistemas que consomem logs estruturados.

    Returns:
        logging.Logger: Instância configurada com os handlers solicitados.

    Example — uso padrão com Rich:
        >>> logger = get_logger(__name__)
        >>> logger.info("Conectado ao MinIO")

    Example — arquivo + Rich:
        >>> logger = get_logger(__name__, log_file="logs/app.log")
        >>> logger.warning("Bucket não encontrado")

    Example — JSON para Airflow:
        >>> logger = get_logger(__name__, json_format=True)
        >>> logger.info("Task iniciada")
        {"ts": "2026-06-19T12:00:00+00:00", "level": "INFO", ...}
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        logger.setLevel(level)
        return logger

    # --- handler de console ---
    if json_format:
        console_handler: logging.Handler = logging.StreamHandler()
        console_handler.setFormatter(_JsonFormatter())
    else:
        console_handler = RichHandler(
            console=_console,
            rich_tracebacks=True,
            show_path=True,
            markup=True,
            log_time_format="[%X]",
        )
        console_handler.setFormatter(
            logging.Formatter("%(message)s", datefmt="%X")
        )

    logger.addHandler(console_handler)

    # --- handler de arquivo (opcional) ---
    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(_JsonFormatter() if json_format else _FILE_FMT)
        logger.addHandler(file_handler)

    logger.propagate = False
    logger.setLevel(level)
    return logger


class BoundLogger(logging.LoggerAdapter):
    """Logger com contexto fixo em todas as mensagens.

    Substitui loguru.Logger.bind() mantendo compatibilidade com logging padrão.
    Prefixo format: [chave=valor | chave=valor] mensagem
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        if self.extra:
            ctx = " | ".join(f"{k}={v}" for k, v in self.extra.items())
            return f"[{ctx}] {msg}", kwargs
        return msg, kwargs

    def bind(self, **kwargs: Any) -> "BoundLogger":
        """Retorna um novo BoundLogger com contexto adicional mesclado."""
        merged = {**self.extra, **kwargs}
        return BoundLogger(self.logger, merged)

    @contextmanager
    def contextualize(self, **kwargs: Any) -> Iterator[None]:
        """Context manager de compatibilidade (loguru.contextualize).

        No logging padrão não há propagação automática de contexto por thread,
        então apenas executa o bloco sem efeito colateral.
        """
        yield


def bind(logger_instance: logging.Logger, **context: Any) -> BoundLogger:
    """Retorna um BoundLogger com contexto fixo — substitui loguru.Logger.bind().

    Args:
        logger_instance: Logger base retornado por get_logger().
        **context: Pares chave=valor adicionados como prefixo em cada mensagem.

    Example:
        >>> log = bind(get_logger(), pipeline="sap_ekko", run_id="abc123")
        >>> log.info("Iniciando")   # → [pipeline=sap_ekko | run_id=abc123] Iniciando
    """
    return BoundLogger(logger_instance, context)


def print_table(
    data: Sequence[Mapping[Hashable, object]],
    title: str | None = None,
    json_format: bool = False,
) -> None:
    """Exibe uma lista de dicts como tabela Rich ou JSON estruturado.

    As colunas são derivadas automaticamente das chaves do primeiro item.
    Em modo JSON (ex: Airflow), emite uma linha JSON por registro.

    Args:
        data: Lista de dicts com os dados a exibir.
        title: Título opcional da tabela (ignorado em modo JSON).
        json_format: Se True, emite JSON ao invés de tabela Rich.

    Example — tabela Rich:
        >>> print_table([{"arquivo": "a.csv", "tamanho": "1 MB"}], title="Arquivos")

    Example — JSON para Airflow:
        >>> print_table(rows, json_format=True)
        {"arquivo": "a.csv", "tamanho": "1 MB"}
    """
    if not data:
        return

    if json_format:
        for row in data:
            print(json.dumps(row, ensure_ascii=False, default=str))
        return

    all_columns = list(data[0].keys())
    term_width = _console.width or 120
    max_cols = max(1, term_width // 12)
    truncated = len(all_columns) > max_cols
    columns = all_columns[:max_cols]

    display_title = f"{title} ({len(all_columns)} colunas, exibindo {max_cols})" if truncated else title
    table = Table(
        title=display_title,
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        show_lines=True,
    )
    for col in columns:
        table.add_column(str(col), min_width=8, max_width=30)
    for row in data:
        table.add_row(*[str(row.get(col, "")) for col in columns])

    _console.print(table)


if __name__ == "__main__":
    logger = get_logger("exemplo", log_file="logs/exemplo.log")
    logger.debug("Mensagem de debug")
    logger.info("Mensagem de info")
    logger.warning("Mensagem de warning")
    logger.error("Mensagem de error")
    logger.critical("Mensagem de critical")

    arquivos = [
        {"arquivo": "dados.csv", "tamanho": "1.2 MB", "modificado": "2026-06-19"},
        {"arquivo": "backup.tar.gz", "tamanho": "340 MB", "modificado": "2026-06-18"},
    ]
    print_table(arquivos, title="Arquivos no bucket")

    logger_json = get_logger("exemplo-json", json_format=True)
    logger_json.info("Modo JSON ativo")
    print_table(arquivos, json_format=True)
