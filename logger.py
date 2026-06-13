"""Módulo de gestão de logs centralizado utilizando Logging padrão do Python.
Oferece suporte a logs coloridos no terminal e logs estruturados em JSON,
priorizando o estilo e formatação do logging_custom.py e mantendo compatibilidade
com a interface do Loguru.
"""

import os
import sys
import json
import logging
import contextvars
from typing import Dict, Any, Union, Optional
from contextlib import contextmanager
from dotenv import load_dotenv

# Carregar variáveis de ambiente para configuração dinâmica
load_dotenv()

# Configuração de encoding UTF-8 para stdout (suporte a Emojis no Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

__all__ = ["LoggerService", "ColoredFormatter", "JsonFormatter", "get_logger"]

RESET = "\033[0m"
BOLD = "\033[1m"

# Cores e Emojis do logging_custom
COLORS: Dict[str, str] = {
    "DEBUG": "\033[94m",      # Azul
    "INFO": "\033[92m",       # Verde
    "WARNING": "\033[93m",    # Amarelo
    "ERROR": "\033[91m",      # Vermelho
    "CRITICAL": "\033[95m",   # Magenta
}

# Cor de fundo para erros críticos
BACKGROUND: Dict[str, str] = {
    "ERROR": "\033[41m",      # Fundo vermelho
    "CRITICAL": "\033[45m",   # Fundo magenta
}

ICONS: Dict[str, str] = {
    "DEBUG": "\U0001f41e",     # 🐞
    "INFO": "\U0001f4a1",      # 💡
    "WARNING": "\U0001f6a8",   # 🚨
    "ERROR": "\U0000274c",     # ❌
    "CRITICAL": "\U0001f4a5",  # 💥
}

# Formatos específicos para cada nível
FORMATS: Dict[str, str] = {
    "DEBUG": "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s",
    "INFO": "%(asctime)s - %(levelname)s - %(message)s",
    "WARNING": "%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    "ERROR": "%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    "CRITICAL": "%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
}

STANDARD_LOG_RECORD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module",
    "msecs", "message", "msg", "name", "pathname", "process",
    "processName", "relativeCreated", "stack_info", "thread", "threadName", "taskName"
}

# Variável de contexto assíncrono/thread-safe para conter metadados extras (Loguru contextualize)
_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar("log_context", default={})


class JsonFormatter(logging.Formatter):
    """Formatter to output logs in JSON format."""

    def __init__(self, date_format: str = "%Y-%m-%d %H:%M:%S") -> None:
        super().__init__(datefmt=date_format)

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt or "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Sempre incluir informações detalhadas para logs de erro ou superior, e debug
        if record.levelno >= logging.ERROR or record.levelno <= logging.DEBUG:
            log_record["file"] = record.filename
            log_record["path"] = record.pathname
            log_record["line"] = record.lineno
            log_record["function"] = record.funcName

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Incluir quaisquer campos "extra" que foram passados ou vinculados
        for key, value in record.__dict__.items():
            if key not in STANDARD_LOG_RECORD_ATTRS:
                log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """Formatter to output logs in a beautiful, highlighted terminal format."""

    def __init__(
        self, use_background: bool = False, date_format: str = "%Y-%m-%d %H:%M:%S"
    ) -> None:
        super().__init__()
        self.use_background = use_background
        self.date_format = date_format

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, RESET)
        background = BACKGROUND.get(record.levelname, "") if self.use_background else ""
        icon = ICONS.get(record.levelname, "")

        # Usar formato específico para cada nível
        format_str = FORMATS.get(record.levelname, FORMATS["INFO"])
        formatter = logging.Formatter(format_str, datefmt=self.date_format)
        message = formatter.format(record)

        if record.levelno >= logging.ERROR:
            extra = (
                "\n%s↳ Arquivo : %s"
                "\n↳ Linha   : %s"
                "\n↳ Função  : %s%s"
                % (
                    background,
                    record.pathname,
                    str(record.lineno),
                    record.funcName,
                    RESET,
                )
            )
            if record.levelno >= logging.CRITICAL and record.exc_info:
                extra += "\n%s%s%s" % (background, BOLD, RESET)
            message += extra

        # Adicionar formatação para extras / contexto do bind
        extras = {k: v for k, v in record.__dict__.items() if k not in STANDARD_LOG_RECORD_ATTRS}
        if extras:
            message += f" | extras={extras}"

        return f"{color}{background}{BOLD}{icon} {message}{RESET}"


class LoguruCompatibleLogger:
    """Wrapper em torno de um logging.Logger padrão do Python.

    Fornece compatibilidade com chamadas de estilo do Loguru, como
    `.bind(**kwargs)` e `.contextualize(**kwargs)`.
    """

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None) -> None:
        self._logger = logger
        self._extra = extra or {}

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)

    def log(self, level: Union[str, int], msg: Any, *args: Any, **kwargs: Any) -> None:
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._log(level, msg, *args, **kwargs)

    def bind(self, **kwargs: Any) -> "LoguruCompatibleLogger":
        """Associa metadados de contexto permanente a esta instância do logger (copiando-a)."""
        new_extra = {**self._extra, **kwargs}
        return LoguruCompatibleLogger(self._logger, new_extra)

    @contextmanager
    def contextualize(self, **kwargs: Any) -> Any:
        """Gerenciador de contexto para associar dados dinâmicos de forma temporária e thread-safe."""
        current = _context.get()
        token = _context.set({**current, **kwargs})
        try:
            yield
        finally:
            _context.reset(token)

    def _log(self, level: int, msg: Any, *args: Any, **kwargs: Any) -> None:
        if not self._logger.isEnabledFor(level):
            return

        call_extra = kwargs.pop("extra", None) or {}

        # Mesclar fontes de metadados extras:
        # 1. contextualize() (ContextVars)
        # 2. bind() (self._extra)
        # 3. extra parameter passed dynamically
        merged_extra = {}
        merged_extra.update(_context.get())
        merged_extra.update(self._extra)
        merged_extra.update(call_extra)

        kwargs["extra"] = merged_extra

        # Corrige o nível da pilha para exibir o arquivo/linha correto do chamador original
        if "stacklevel" not in kwargs:
            kwargs["stacklevel"] = 3  # wrapper -> method (ex. info) -> _log -> logger.log

        self._logger.log(level, msg, *args, **kwargs)

    # Delegadores adicionais para manter compatibilidade com propriedades de logging padrão
    @property
    def handlers(self) -> Any:
        return self._logger.handlers

    @property
    def level(self) -> int:
        return self._logger.level

    def setLevel(self, level: Union[str, int]) -> None:
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._logger.setLevel(level)

    def addHandler(self, hdlr: logging.Handler) -> None:
        self._logger.addHandler(hdlr)

    def removeHandler(self, hdlr: logging.Handler) -> None:
        self._logger.removeHandler(hdlr)


class LoggerService:
    """Configurador e gerador de Loggers padrão com formatação rica do logging_custom."""

    def __init__(
        self,
        name: str = "app",
        level: Union[str, int] = "INFO",
        use_background: bool = True,
        use_json: bool = False,
        date_format: str = "%Y-%m-%d %H:%M:%S",
        enable_file_logging: bool = False,
        log_file: str = "app.log",
    ) -> None:
        self.logger = logging.getLogger(name)

        if isinstance(level, str):
            level = level.upper()
            level = getattr(logging, level, logging.INFO)

        self.logger.setLevel(level)  # type: ignore
        self.logger.propagate = False

        # Evita a duplicação de handlers se este logger já foi inicializado
        if self.logger.handlers:
            self.logger.handlers.clear()

        # Determinar formatador de console
        if use_json:
            console_formatter: logging.Formatter = JsonFormatter(date_format=date_format)
        else:
            console_formatter = ColoredFormatter(
                use_background=use_background, date_format=date_format
            )

        # Handler de Console (Standard Output)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Handler de Ficheiro (Opcional)
        if enable_file_logging and log_file:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            if use_json:
                file_formatter: logging.Formatter = JsonFormatter(date_format=date_format)
            else:
                file_formatter = logging.Formatter(
                    "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s",
                    datefmt=date_format,
                )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def get_logger(self) -> LoguruCompatibleLogger:
        return LoguruCompatibleLogger(self.logger)


# Configuração automática baseada em variáveis de ambiente
def _initialize_global_logger() -> LoguruCompatibleLogger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_to_json = os.getenv("LOG_TO_JSON", "FALSE").upper() == "TRUE"
    log_path = os.getenv("LOG_PATH", "logs/pipeline.log")
    
    # Se log_to_json for ativado e estiver usando o arquivo default, rotacionamos para .json
    if log_to_json and log_path == "logs/pipeline.log":
        log_path = "logs/pipeline.json"

    # Sempre ativa escrita em ficheiro se LOG_PATH estiver definido
    enable_file = bool(log_path)

    service = LoggerService(
        name="pipeline_ingestion",
        level=log_level,
        use_background=True,
        use_json=log_to_json,
        enable_file_logging=enable_file,
        log_file=log_path,
    )
    return service.get_logger()


# Instância global unificada
_global_logger = _initialize_global_logger()


def get_logger(*args: Any, **kwargs: Any) -> LoguruCompatibleLogger:
    """Retorna a instância configurada do logger.

    Suporta argumentos opcionais para inicializar adaptadores com pipeline, job ou run_id específicos.
    """
    if not args and not kwargs:
        return _global_logger

    name = args[0] if args else kwargs.get("name")
    pipeline = kwargs.get("pipeline")
    job = kwargs.get("job")
    run_id = kwargs.get("run_id")

    # Se apenas metadados de bind foram especificados (sem nome diferente de "pipeline_ingestion"),
    # reutilizamos o _global_logger e apenas fazemos bind para evitar recriar os handlers de arquivo e console.
    if (name is None or name == "pipeline_ingestion") and (pipeline or job or run_id):
        l = _global_logger
        bind_kwargs = {}
        if pipeline:
            bind_kwargs["pipeline"] = pipeline
        if job:
            bind_kwargs["job"] = job
        if run_id:
            bind_kwargs["run_id"] = run_id
        return l.bind(**bind_kwargs)

    # Caso contrário, cria um novo LoggerService (ex: se um nome de sub-logger específico for pedido)
    target_name = name or "pipeline_ingestion"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_to_json = os.getenv("LOG_TO_JSON", "FALSE").upper() == "TRUE"
    log_path = os.getenv("LOG_PATH", "logs/pipeline.log")
    enable_file = bool(log_path)

    # Se log_to_json for ativado e estiver usando o arquivo default, rotacionamos para .json
    if log_to_json and log_path == "logs/pipeline.log":
        log_path = "logs/pipeline.json"

    service = LoggerService(
        name=target_name,
        level=log_level,
        use_background=True,
        use_json=log_to_json,
        enable_file_logging=enable_file,
        log_file=log_path,
    )
    l = service.get_logger()
    
    bind_kwargs = {}
    if pipeline:
        bind_kwargs["pipeline"] = pipeline
    if job:
        bind_kwargs["job"] = job
    if run_id:
        bind_kwargs["run_id"] = run_id
        
    if bind_kwargs:
        l = l.bind(**bind_kwargs)
    return l


if __name__ == "__main__":
    # Teste de uso normal (Colorido)
    print("--- Teste Formato Colorido ---")
    log = get_logger()
    log.debug("Debug message")
    log.info("Info message com extra", extra={"user": "admin", "id": 123})
    log.warning("Warning message")

    # Testar .bind() e .contextualize()
    bound = log.bind(run_id="uuid-123456", pipeline="pipeline_sap")
    bound.info("Mensagem com contexto fixo (bind)")

    with log.contextualize(job="SAP_EXTRACT"):
        log.info("Dentro do contextualize (deve ter job)")
        bound.warning("Bound logger dentro do contextualize")

    log.info("Fora do contextualize (não deve ter job)")

    log.error("Error message")
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("Exception message")

    # Limpar handlers para testar json no mesmo script
    log.handlers.clear()

    # Teste de uso JSON
    print("\n--- Teste Formato JSON ---")
    os.environ["LOG_TO_JSON"] = "TRUE"
    # Obter logger de teste JSON
    json_log = get_logger("json_test")
    json_log.debug("Debug JSON message")
    json_log.info("Info JSON message com extra", extra={"user": "admin", "id": 123})
    json_log.warning("Warning JSON message")
    json_log.error("Error JSON message")
    try:
        1 / 0
    except ZeroDivisionError:
        json_log.exception("Exception JSON message")
