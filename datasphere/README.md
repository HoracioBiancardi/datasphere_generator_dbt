Certifique-se de ter o uv instalado em sua máquina. Caso não possua, instale via:

```bash
# macOS/Linux
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm [https://astral.sh/uv/install.ps1](https://astral.sh/uv/install.ps1) | iex"
```

Com o uv pronto, sincronize o ambiente e instale as dependências executando o comando na raiz do projeto:

```bash
uv sync
```

## 💡 Como Usar (Exemplo Seguro)
Crie um arquivo main.py na raiz do projeto para consumir o módulo:

```python
import os
from datasphere import DatasphereConnector, DatasphereExtractor

def main():
    # Configurações obtidas idealmente de variáveis de ambiente
    db_config = {
        "host": os.getenv("DATASPHERE_HOST", "seu-host.hana.ondemand.com"),
        "port": int(os.getenv("DATASPHERE_PORT", "443")),
        "user": os.getenv("DATASPHERE_USER", "DB_USER"),
        "password": os.getenv("DATASPHERE_PASSWORD", "SenhaForte"),
        "schema": os.getenv("DATASPHERE_SCHEMA", "VBI_S_DATA"),
    }

    # Inicialização modular
    connector = DatasphereConnector(config=db_config)
    extractor = DatasphereExtractor(connector=connector)

    # Query parametrizada para evitar SQL Injection
    query = \"\"\"
        SELECT * FROM BI_LARGE_SALES_FACT
        WHERE STATUS = :status AND REGION = :regiao
    \"\"\"

    parametros = {
        "status": "ACTIVE",
        "regiao": "SUL"
    }

    print("--- Iniciando Extração Eficiente em Chunks ---")

    # Execução estratégica consumindo os geradores por demanda de memória
    for idx, chunk_df in enumerate(extractor.execute_query_in_chunks(query, params=parametros, chunk_size=50000)):
        print(f"[Chunk #{idx + 1}] Carregado com sucesso. Linhas: {len(chunk_df)}")
        # Processe seu DataFrame aqui (Ex: salvar em parquet, descarregar no S3, etc.)

if __name__ == "__main__":
    main()
```
Para rodar o script garantindo o ambiente isolado:

```bash
uv run main.py
```

## 🛡️ Segurança e Resiliência Implementadas
Prevenção de SQL Injection: Utiliza Named Bind Parameters (:parametro) processados nativamente pela camada de execução do SQLAlchemy, impossibilitando a execução de scripts maliciosos injetados por variáveis.

Resiliência e Retries: O decorador @retry monitora quedas de conexões operacionais (OperationalError, DBAPIError) efetuando tentativas automáticas com Exponential Backoff antes de falhar a aplicação.

Gerenciamento de Memória: O método execute_query_in_chunks utiliza a propriedade yield_per combinada com cursores streaming do banco de dados, evitando estouro de memória RAM ao processar milhões de registros.
"""
