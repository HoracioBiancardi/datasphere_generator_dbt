"""Module for managing SAP Datasphere database connections and engine lifecycle."""

from typing import Any, Dict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from logger import get_logger

logger = get_logger()


class DatasphereConnector:
    """Manages the lifecycle, pooling, and resilience of SAP Datasphere connections."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initializes the connector with database configurations.

        Args:
            config: Dictionary containing 'host', 'port', 'user', 'password',
                    and optionally 'schema'.
        """
        self.config = config
        self._engine: Engine | None = None

        # Constrói a URL de conexão nativa para o driver hdbcli da SAP
        self._connection_url = (
            f"hana://{config['user']}:{config['password']}@"
            f"{config['host']}:{config['port']}/"
        )
        if "schema" in config:
            self._connection_url += f"?currentSchema={config['schema']}"

    def get_engine(self) -> Engine:
        """Lazy initialization of the SQLAlchemy Engine with robust connection pooling.

        Returns:
            Engine: The SQLAlchemy engine instance ready for execution.
        """
        if self._engine is None:
            logger.info("Initializing Datasphere SQLAlchemy Engine.")
            self._engine = create_engine(
                self._connection_url,
                echo=False,
                pool_size=5,          # Mantém até 5 conexões ativas no pool para reutilização
                max_overflow=10,       # Permite até 10 conexões adicionais se houver pico
                pool_pre_ping=True,    # CRÍTICO: Testa a conexão antes de usá-la. Se caiu, reconecta automaticamente.
                pool_recycle=3600,     # Recicla conexões a cada 1 hora para evitar timeouts do lado do SAP
            )
        return self._engine
