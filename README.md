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
       ├─► output/dbt/models/staging/stg_sap_[tabela].sql
       └─► output/dbt/models/staging/schema.yml
```

Os módulos são **totalmente independentes**, conectados apenas por contratos JSON em disco. Cada um pode ser executado isoladamente.

---

## Pré-requisitos

- Python >= 3.10
- [`uv`](https://github.com/astral-sh/uv) instalado

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Instalação

```bash
# Clone o repositório e entre na pasta
git clone <url-do-repo>
cd datasphere_generator_dbt

# Instala dependências e o pacote em modo editável
uv sync
```

---

## Configuração (.env)

Copie `.env` e ajuste os valores:

```dotenv
# ── Conexão com SAP Datasphere (HANA) ────────────────────────────────────────
HANA_ADDRESS=<host>.hana.prod-us10.hanacloud.ondemand.com
HANA_PORT=443
HANA_USER=DWCDBUSER#DATALAKE
HANA_PASSWORD=<senha>

# ── Módulo 1: Extrator DDIC ───────────────────────────────────────────────────
# Schema no Datasphere onde as tabelas DD* estão replicadas
DDIC_SCHEMA=IB_SAPECC
# Idioma das descrições: P=Português, E=Inglês, D=Alemão
DDIC_LANGUAGE=P

# ── Módulo 3: Gerador dbt ─────────────────────────────────────────────────────
# Nome usado em {{ source('sap', 'TABELA') }} nos modelos gerados
DBT_SOURCE_NAME=sap

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_TO_JSON=False
LOG_PATH=log/pipeline.json
```

---

## Execução

### Pipeline completo (recomendado)

Processa uma ou mais tabelas em sequência: DDIC → Tradução → dbt.

```bash
# Uma tabela
uv run main.py MARA

# Múltiplas tabelas
uv run main.py MARA BSEG VBAK EKKO

# Os nomes são normalizados para maiúsculas automaticamente
uv run main.py mara bseg
```

### Executar módulos individualmente (via Python)

Útil quando você já tem o contrato intermediário em disco e quer re-executar apenas parte do pipeline.

**Módulo 1 — apenas extração DDIC:**

```python
from datasphere_extractor import DatasphereConnector, DatasphereExtractor
from sap_generator.ddic_extractor import DDICExtractor

connector = DatasphereConnector({"host": "...", "port": 443, "user": "...", "password": "..."})
extractor = DatasphereExtractor(connector)

ddic = DDICExtractor(extractor=extractor, ddic_schema="IB_SAPECC", language="P")
contract = ddic.extract("MARA")
# Salvo em: output/contracts/ddic/ddic_schema_mara.json
```

**Módulo 2 — apenas tradução (a partir de um JSON já gerado):**

```python
from sap_generator.ingestor import IngestorTranslator

translator = IngestorTranslator()
pipeline = translator.translate_from_file("output/contracts/ddic/ddic_schema_mara.json")
# Salvo em: output/contracts/pipeline/ingestor_pipeline_mara.json
```

**Módulo 3 — apenas geração dbt (a partir de um JSON já gerado):**

```python
from sap_generator.dbt_generator import DbtGenerator

generator = DbtGenerator(source_name="sap")
generator.generate_from_file("output/contracts/pipeline/ingestor_pipeline_mara.json")
# Salvo em: output/dbt/models/staging/stg_sap_mara.sql
#           output/dbt/models/staging/schema.yml
```

---

## Contratos de Dados

### Módulo 1 → `ddic_schema_[tabela].json`

```json
{
  "sap_table_name": "MARA",
  "table_description": "Dados gerais do material",
  "table_class": "TRANSP",
  "data_class": "APPL0",
  "size_category": 3,
  "columns": [
    {
      "field_name": "MATNR",
      "position": 2,
      "is_key": true,
      "sap_type": "CHAR",
      "length": 18,
      "decimals": 0,
      "data_element": "MATNR",
      "field_description": "Número do material",
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
      "field_description": "Data do envio da mercadoria",
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
    "primary_keys": ["mandt", "numero_material"],
    "watermark_column": "data_ultima_modificacao"
  },
  "transformed_columns": [
    {
      "source_field": "MATNR",
      "target_field": "numero_material",
      "target_type": "STRING",
      "sql_expression": "CAST(matnr AS STRING)",
      "description": "Número do material"
    },
    {
      "source_field": "ZZ_DT_ENVIO",
      "target_field": "data_envio_mercadoria",
      "target_type": "DATE",
      "sql_expression": "CASE WHEN zz_dt_envio = '00000000' OR zz_dt_envio = '' THEN NULL ELSE TO_DATE(zz_dt_envio, 'YYYYMMDD') END",
      "description": "Data do envio da mercadoria (Convertido de CHAR)"
    }
  ]
}
```

### Módulo 3 → `stg_sap_mara.sql`

```sql
{{ config(
    materialized='incremental',
    unique_key=['mandt', 'numero_material'],
    incremental_strategy='merge'
) }}

SELECT
    CAST(mandt AS STRING) AS mandt,
    CAST(matnr AS STRING) AS numero_material,
    CASE WHEN zz_dt_envio = '00000000' OR zz_dt_envio = '' THEN NULL ELSE TO_DATE(zz_dt_envio, 'YYYYMMDD') END AS data_envio_mercadoria
FROM {{ source('sap', 'MARA') }}
{%- if is_incremental() %}
WHERE data_ultima_modificacao > (SELECT MAX(data_ultima_modificacao) FROM {{ this }})
{%- endif %}
```

### Módulo 3 → `schema.yml`

```yaml
version: 2

models:
  - name: stg_sap_mara
    description: Dados gerais do material
    columns:
      - name: mandt
        description: Mandante
        tests:
          - unique
          - not_null
      - name: numero_material
        description: Número do material
        tests:
          - unique
          - not_null
      - name: data_envio_mercadoria
        description: Data do envio da mercadoria (Convertido de CHAR)
```

---

## Regras de Negócio

### Módulo 1 — Heurística de Datas Ocultas

Campos `CHAR` ou `NUMC` com tamanho entre 8 e 10 caracteres são marcados com `possivel_data: true` quando o nome do elemento de dados (ROLLNAME), domínio (DOMNAME) ou descrição (DDTEXT) contém qualquer um dos termos:

`DATA`, `DT`, `DATUM`, `TIMESTAMP`, `DATE`, `CRIADO`, `MODIFICADO`

### Módulo 2 — Tipo de Carga

| Condição | load_type |
|---|---|
| `table_class` é `VIEW` ou `INTTAB` | `FULL` |
| `data_class` é `APPL2` (Customização) | `FULL` |
| `data_class` é `APPL1` (Transacional) | `INCREMENTAL` |
| `size_category` >= 3 | `INCREMENTAL` |
| Demais casos (APPL0 — Dados Mestre) | `FULL` |

### Módulo 2 — Mapeamento de Tipos SAP → dbt

| Tipo SAP | Tipo alvo | Expressão SQL |
|---|---|---|
| `CLNT`, `CHAR`, `NUMC`, `TIMS` | `STRING` | `CAST(campo AS STRING)` |
| `DATS` | `DATE` | `CASE WHEN campo = '00000000' ... ELSE TO_DATE(campo, 'YYYYMMDD') END` |
| `CURR`, `QUAN`, `DEC` | `DECIMAL(len, dec)` | `CAST(campo AS DECIMAL(len, dec))` |
| `INT1`, `INT2`, `INT4`, `INT8` | `INTEGER` | `CAST(campo AS INTEGER)` |
| `possivel_data: true` | `DATE` | mesma expressão que `DATS` |

### Módulo 2 — Watermark (cargas incrementais)

Prioridade de seleção do campo watermark:

1. Campo SAP padrão presente na tabela: `AEDAT` → `ERDAT` → `CPUDT` → `UDATE` → `BUDAT`
2. Primeiro campo com `possivel_data: true`
3. `null` se nenhum candidato for encontrado

---

## Estrutura do Projeto

```
datasphere_generator_dbt/
├── datasphere/
│   └── datasphere_extractor/   # Conector e extrator base (HANA/SQLAlchemy)
├── sap_generator/
│   ├── ddic_extractor/         # Módulo 1: queries DDIC + heurística de datas
│   ├── ingestor/               # Módulo 2: mapeamento de tipos + estratégia de carga
│   └── dbt_generator/          # Módulo 3: geração de .sql e schema.yml
├── output/
│   ├── contracts/
│   │   ├── ddic/               # ddic_schema_*.json
│   │   └── pipeline/           # ingestor_pipeline_*.json
│   └── dbt/
│       └── models/staging/     # stg_sap_*.sql + schema.yml
├── logger.py
├── main.py                     # Orquestrador CLI
└── pyproject.toml
```
