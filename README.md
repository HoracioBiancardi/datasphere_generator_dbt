# datasphere-generator-dbt

Framework modular de engenharia de dados que extrai metadados do Dicionário de Dados SAP (DDIC) via **SAP Datasphere**, traduz os tipos e estratégias de carga, e gera automaticamente modelos de staging para **dbt**.

---

## Arquitetura

```
[SAP ERP / DDIC]
       │
       ▼  (queries em DD02L, DD02T, DD03L, DD04T, DD09L)
┌──────────────────────────────────────┐
│  MÓDULO 1 — Extrator DDIC            │  sap_generator/ddic_extractor/
│  DDICExtractor                       │
└──────────────────────────────────────┘
       │
       ▼  output/contracts/ddic/ddic_schema_[tabela].json
┌──────────────────────────────────────┐
│  MÓDULO 2 — Ingestor & Tradutor      │  sap_generator/ingestor/
│  IngestorTranslator                  │
└──────────────────────────────────────┘
       │
       ▼  output/contracts/pipeline/ingestor_pipeline_[tabela].json
┌──────────────────────────────────────┐
│  MÓDULO 3 — Gerador de Artefatos dbt │  sap_generator/dbt_generator/
│  DbtGenerator                        │
└──────────────────────────────────────┘
       │
       ├─► output/dbt/models/staging/[TABELA]/stg_sap_[tabela].sql
       └─► output/dbt/models/staging/[TABELA]/stg_sap_[tabela].yml
```

Os módulos são **totalmente independentes**, conectados apenas por contratos JSON em disco. Cada um pode ser executado isoladamente via CLI ou Python.

---

## Pré-requisitos

- Python >= 3.10
- [`uv`](https://github.com/astral-sh/uv) instalado

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Instalação

```bash
git clone <url-do-repo>
cd datasphere_generator_dbt

uv sync
```

Após o `uv sync`, o comando `datasphere-dbt` fica disponível no ambiente virtual.

---

## Configuração (.env)

Crie um arquivo `.env` na raiz do projeto:

```dotenv
# ── Conexão com SAP Datasphere (HANA) ─────────────────────────────────────
HANA_ADDRESS=<host>.hana.prod-us10.hanacloud.ondemand.com
HANA_PORT=443
HANA_USER=DWCDBUSER#DATALAKE
HANA_PASSWORD=<senha>

# ── Módulo 1: Extrator DDIC ───────────────────────────────────────────────
# Schema no Datasphere onde as tabelas DD* estão replicadas
DDIC_SCHEMA=IB_SAPECC
# Idioma das descrições: P=Português, E=Inglês, D=Alemão
DDIC_LANGUAGE=P

# ── Módulo 3: Gerador dbt ─────────────────────────────────────────────────
DBT_SOURCE_NAME=dataspherev2
DBT_DATABASE=BRONZE
DBT_SCHEMA=dataspherev2

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_TO_JSON=False
LOG_PATH=log/pipeline.json
```

---

## CLI

O projeto expõe o comando `datasphere-dbt` com quatro subcomandos.

### `run` — pipeline completo (recomendado)

Executa os três módulos em sequência para uma ou mais tabelas SAP.

```bash
# Uma tabela
uv run datasphere-dbt run MARA

# Múltiplas tabelas (nomes normalizados para maiúsculas automaticamente)
uv run datasphere-dbt run MARA BSEG VBAK EKKO

# Sobrescrevendo defaults sem .env
uv run datasphere-dbt run MARA \
  --ddic-schema IB_SAPECC \
  --source-name dataspherev2 \
  --database BRONZE \
  --schema dataspherev2
```

```
Opções:
  --ddic-schema TEXT     Schema DDIC no Datasphere  [env: DDIC_SCHEMA, obrigatório]
  --language TEXT        Idioma das descrições       [env: DDIC_LANGUAGE, padrão: P]
  --source-name TEXT     Nome do source dbt          [env: DBT_SOURCE_NAME, padrão: dataspherev2]
  --database TEXT        Database dbt                [env: DBT_DATABASE, padrão: BRONZE]
  --schema TEXT          Schema dbt                  [env: DBT_SCHEMA, padrão: dataspherev2]
  --ddic-output DIR      Destino contratos DDIC      [padrão: output/contracts/ddic]
  --pipeline-output DIR  Destino contratos pipeline  [padrão: output/contracts/pipeline]
  --dbt-output DIR       Destino artefatos dbt       [padrão: output/dbt/models/staging]
```

### `ddic` — apenas Módulo 1

Extrai metadados DDIC do SAP e salva os contratos JSON.

```bash
uv run datasphere-dbt ddic MARA BSEG
```

### `translate` — apenas Módulo 2

Lê contratos DDIC e gera contratos de pipeline. Aceita nomes de tabela (busca no `--ddic-dir`) ou arquivos diretos.

```bash
# A partir do diretório padrão
uv run datasphere-dbt translate MARA

# A partir de arquivos específicos
uv run datasphere-dbt translate \
  --from-file output/contracts/ddic/ddic_schema_mara.json \
  --from-file output/contracts/ddic/ddic_schema_bseg.json
```

### `generate` — apenas Módulo 3

Gera `.sql` e `sources.yml` dbt. Aceita nomes de tabela ou arquivos diretos.

```bash
# A partir do diretório padrão
uv run datasphere-dbt generate MARA

# A partir de um arquivo específico
uv run datasphere-dbt generate --from-file output/contracts/pipeline/ingestor_pipeline_mara.json

# Customizando os parâmetros dbt
uv run datasphere-dbt generate MARA \
  --source-name minha_fonte \
  --database SILVER \
  --schema sap_staging
```

### Ajuda

Qualquer subcomando aceita `--help`:

```bash
uv run datasphere-dbt --help
uv run datasphere-dbt run --help
uv run datasphere-dbt generate --help
```

---

## Contratos de Dados

### Módulo 1 → `ddic_schema_[tabela].json`

```json
{
  "sap_table_name": "MARA",
  "table_description": "Dados gerais do material",
  "table_class": "TRANSP",
  "table_class_label": "Tabela Transparente (Física)",
  "data_class": "APPL0",
  "data_class_label": "Dados Mestre (Master Data)",
  "size_category": 3,
  "size_category_label": "Até 650.000 registros",
  "primary_keys": ["MANDT", "MATNR"],
  "columns": [
    {
      "field_name": "MATNR",
      "position": 2,
      "is_key": true,
      "sap_type": "CHAR",
      "length": 18,
      "decimals": 0,
      "data_element": "MATNR",
      "domain_name": "MATNR",
      "field_description": "Número do material",
      "field_label": "Material",
      "possivel_data": false
    },
    {
      "field_name": "ZZ_DT_ENVIO",
      "position": 12,
      "is_key": false,
      "sap_type": "CHAR",
      "length": 8,
      "decimals": 0,
      "data_element": "ZCHAR8",
      "domain_name": "ZCHAR8",
      "field_description": "Data do envio da mercadoria",
      "field_label": "Dt. Envio",
      "possivel_data": true
    }
  ]
}
```

### Módulo 2 → `ingestor_pipeline_[tabela].json`

```json
{
  "target_table": "stg_sap_mara",
  "source_sap_table": "MARA",
  "table_description": "Dados gerais do material",
  "ingestion_strategy": {
    "load_type": "INCREMENTAL",
    "primary_keys": ["MANDT", "MATNR"],
    "watermark_column": "data_ultima_modificacao"
  },
  "transformed_columns": [
    {
      "source_field": "MATNR",
      "target_field": "material",
      "target_type": "STRING",
      "sql_expression": "MATNR",
      "description": "Número do material"
    },
    {
      "source_field": "ZZ_DT_ENVIO",
      "target_field": "dt_envio",
      "target_type": "DATE",
      "sql_expression": "CASE WHEN ZZ_DT_ENVIO = '00000000' OR ZZ_DT_ENVIO = '' THEN NULL ELSE TO_DATE(ZZ_DT_ENVIO, 'YYYYMMDD') END",
      "description": "Data do envio da mercadoria"
    }
  ]
}
```

### Módulo 3 → `stg_sap_mara.sql` (INCREMENTAL)

```sql
{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        alias='mara'
        tags=['sap','datasphere','silver', 'MARA']
        unique_key='mandt',
    )
}}
{% if is_incremental() %}
    WITH novos_hashes AS (
        SELECT s_tgt.hash_pk
        FROM {{ source('dataspherev2', 'mara') }} AS s_tgt
        WHERE TRY_CONVERT(DATETIME2, s_tgt.dt_ingestao) >= (
                SELECT DATEADD(
                    DAY, -1, MAX(s_src.dt_ingestao)
                ) FROM {{ this }} AS s_src
            )
    )
{% endif %}

SELECT
    MANDT AS mandt,
    MATNR AS material,
    CASE WHEN ZZ_DT_ENVIO = '00000000' OR ZZ_DT_ENVIO = '' THEN NULL ELSE TO_DATE(ZZ_DT_ENVIO, 'YYYYMMDD') END AS dt_envio
FROM {{ source('dataspherev2', 'MARA') }}
{%- if is_incremental() %}
WHERE data_ultima_modificacao > (SELECT MAX(data_ultima_modificacao) FROM {{ this }})
{%- endif %}
```

### Módulo 3 → `stg_sap_mara.yml` (sources)

```yaml
sources:
  - name: dataspherev2
    database: BRONZE
    schema: dataspherev2
    tables:
      - name: mara
        description: "Dados gerais do material"
        config:
          materialized: incremental
          incremental_strategy: "delete+insert"
          unique_key: "hash_pk"
          tags: ["dataspherev2", "silver"]

        columns:
          # Chaves Primárias / Identificadores
          - name: mandt
            description: "Mandante"
          - name: material
            description: "Número do material"
          - name: dt_envio
            description: "Data do envio da mercadoria"
```

---

## Regras de Negócio

### Módulo 1 — Heurística de Datas Ocultas

Campos `CHAR` ou `NUMC` com tamanho entre 8 e 10 caracteres são marcados com `possivel_data: true` quando o nome do elemento de dados (ROLLNAME), domínio (DOMNAME) ou descrição (DDTEXT) contém qualquer um dos termos:

`DATA`, `DT`, `DATUM`, `TIMESTAMP`, `DATE`, `CRIADO`, `MODIFICADO`

### Módulo 1 — Nomenclatura de Colunas (`field_label`)

O nome-alvo da coluna no dbt é gerado a partir do texto curto de tela do campo (SCRTEXT_M → SCRTEXT_L → DDTEXT), convertido para `snake_case`. Isso produz nomes mais concisos que o texto longo original.

### Módulo 2 — Tipo de Carga

| Condição | load_type |
|---|---|
| `table_class` é `VIEW` ou `INTTAB` | `FULL` |
| `data_class` é `APPL0` (Dados Mestre) | `FULL` |
| `data_class` é `APPL2` (Customização) | `FULL` |
| `data_class` é `APPL1` (Transacional) | `INCREMENTAL` |
| `size_category` >= 3 | `INCREMENTAL` |
| Demais casos | `FULL` |

### Módulo 2 — Mapeamento de Tipos SAP → dbt

| Tipo SAP | Tipo alvo | Expressão SQL |
|---|---|---|
| `CLNT`, `CHAR`, `NUMC`, `TIMS`, `UNIT`, `CUKY`, `LANG`, `ACCP` | `STRING` | referência direta (já é NVARCHAR no HANA) |
| `DATS` | `DATE` | `CASE WHEN campo = '00000000' ... ELSE TO_DATE(campo, 'YYYYMMDD') END` |
| `CURR`, `QUAN`, `DEC` | `DECIMAL(len, dec)` | `CAST(campo AS DECIMAL(len, dec))` |
| `INT1`, `INT2`, `INT4`, `INT8` | `INTEGER` | `CAST(campo AS INTEGER)` |
| `possivel_data: true` | `DATE` | mesma expressão que `DATS` |
| Outros | `STRING` | referência direta |

> Tipos de texto SAP são nativamente `NVARCHAR` no HANA/Datasphere — nenhum `CAST` é emitido para eles.

### Módulo 2 — Watermark (cargas incrementais)

Prioridade de seleção do campo watermark:

1. Campo SAP padrão presente na tabela: `AEDAT` → `ERDAT` → `CPUDT` → `UDATE` → `BUDAT` → `UPDDT`
2. Primeiro campo com `possivel_data: true`
3. `null` se nenhum candidato for encontrado

---

## Logging

O módulo `logger.py` fornece logging com **Rich** no terminal e saída opcional em JSON para sistemas como Airflow.

```python
from logger import get_logger, bind, print_table

# Logger padrão (Rich colorido no terminal)
logger = get_logger(__name__)
logger.info("Conectado ao Datasphere")

# Com arquivo rotativo (10 MB / 5 backups)
logger = get_logger(__name__, log_file="log/pipeline.log")

# Modo JSON — ideal para Airflow e log aggregators
logger = get_logger(__name__, json_format=True)
# → {"ts": "2026-06-20T10:00:00+00:00", "level": "INFO", "message": "..."}

# Logger com contexto fixo em todas as mensagens
log = bind(logger, pipeline="sap_mara", run_id="abc123")
log.info("Iniciando")
# → [pipeline=sap_mara | run_id=abc123] Iniciando

# Exibe uma lista de dicts como tabela Rich no terminal
print_table([{"tabela": "MARA", "colunas": 42}], title="Resultado")
```

---

## Estrutura do Projeto

```
datasphere_generator_dbt/
├── datasphere/
│   └── datasphere_extractor/   # Conector e extrator base (HANA/SQLAlchemy)
├── sap_generator/
│   ├── ddic_extractor/         # Módulo 1: queries DDIC + heurística de datas
│   ├── ingestor/               # Módulo 2: mapeamento de tipos + estratégia de carga
│   └── dbt_generator/          # Módulo 3: geração de .sql e sources.yml
├── output/
│   ├── contracts/
│   │   ├── ddic/               # ddic_schema_*.json
│   │   └── pipeline/           # ingestor_pipeline_*.json
│   └── dbt/
│       └── models/staging/
│           └── [TABELA]/       # stg_sap_*.sql + stg_sap_*.yml (por tabela)
├── cli.py                      # CLI (datasphere-dbt) — entry point principal
├── logger.py                   # Logging com Rich, arquivo e JSON
├── main.py                     # Orquestrador legado (argparse)
└── pyproject.toml
```
