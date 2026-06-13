"""Module for secure and resilient data extraction."""


from typing import Generator, Any, Dict
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .connection import DatasphereConnector
from logger import get_logger


logger = get_logger()

class DatasphereExtractor:
    """Handles secure data extraction strategies."""

    def __init__(self, connector: DatasphereConnector) -> None:
        self.connector = connector

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((OperationalError, DBAPIError)),
        reraise=True,
    )
    def execute_query_to_df(self, query: str, params: Dict[str, Any] | None = None) -> pd.DataFrame:
        """Executes a standard query safely using bind parameters."""
        engine = self.connector.get_engine()
        query_params = params or {}

        with engine.connect() as connection:
            # text(query) + connection.execute(..., query_params) neutraliza o SQL Injection
            result = connection.execute(text(query), query_params)
            return pd.DataFrame(result.fetchall(), columns=result.keys())

    def execute_query_in_chunks(
        self, query: str, params: Dict[str, Any] | None = None, chunk_size: int = 100000
    ) -> Generator[pd.DataFrame, None, None]:
        """Executes a parameterized query and yields data in chunks safely."""
        engine = self.connector.get_engine()
        query_params = params or {}

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=8),
            retry=retry_if_exception_type((OperationalError, DBAPIError)),
            reraise=True,
        )
        def _get_stream_connection():
            connection = engine.connect()
            execution_options = {"yield_per": chunk_size}
            # Passamos os parâmetros com segurança aqui também
            result_proxy = connection.execution_options(**execution_options).execute(
                text(query), query_params
            )
            return connection, result_proxy

        connection = None
        try:
            connection, result_proxy = _get_stream_connection()
            while True:
                chunk_rows = result_proxy.fetchmany(chunk_size)
                if not chunk_rows:
                    break
                yield pd.DataFrame(chunk_rows, columns=result_proxy.keys())
        except Exception as e:
            logger.error(f"Error during chunked extraction: {e}")
            raise e
        finally:
            if connection:
                connection.close()
