# Politeia

Politeia é uma infraestrutura de inteligência institucional para casas legislativas. Ela conecta fontes públicas
oficiais, normaliza seus dados em uma ontologia comum (pessoas, mandatos, partidos, proposições, eventos), preserva a
evidência original de cada fato e entrega tudo por uma API única e por uma interface que funciona para qualquer
instituição registrada.

Hack Brasil 2026 · trilha **Logística & automação**, para parlamentares, gabinetes e instituições legislativas.

A primeira versão integra **Senado Federal** e **Assembleia Legislativa de Pernambuco (ALEPE)**, alternáveis na mesma
interface sem nenhum código de frontend específico por instituição.

## Arquitetura

```
apps/terminal          React 19 + Vite + Blueprint 6 + D3 + Motion (consome só a API Politeia)
engine/api             FastAPI v1, contratos Pydantic, read-models
engine/ingestion       execuções de ingestão, raw records, persistência idempotente
engine/capabilities    capacidades derivadas da ingestão real (não declaradas)
engine/db              SQLAlchemy 2 + Alembic (schemas registry, ingestion, core, legislative, evidence)
connectors/base        cliente HTTP (allow-list, rate limit, retry/backoff, hashing) e contratos de conector
connectors/senate      conector Dados Abertos do Senado (JSON)
connectors/alepe       conector Dados Abertos da ALEPE (JSON + XML)
institution-packs/*    configuração por instituição: assentos, terminologia, fontes, capacidades esperadas
```

Detalhes em [docs/architecture.md](docs/architecture.md); inventário das fontes em [docs/sources.md](docs/sources.md).

## Como rodar

Pré-requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, Docker.

```bash
# 1. Banco: Postgres local, ou Supabase definindo POLITEIA_DATABASE_URL com a URI do Session pooler
#    (postgresql://... é aceito; o driver psycopg é aplicado automaticamente)
docker compose -f infra/docker-compose.yml up -d
cp .env.example .env

# 2. Engine
uv sync
uv run alembic upgrade head
uv run python -m engine.cli sync            # bootstrap dos packs + ingestão real (membros, depois proposições)
uv run uvicorn engine.api.app:app --port 8000   # OpenAPI em http://localhost:8000/docs

# 3. Interface
cd apps/terminal
npm install
npm run dev                                  # http://localhost:5173 (proxy /v1 -> :8000)
```

Outros comandos:

```bash
uv run python -m engine.cli sync --institution ins_pe_alepe --scope proposals
uv run pytest                                # conectores, pipeline e API (usa o banco politeia_test)
uv run ruff check .
cd apps/terminal && npm test && npm run build
npm run api:types                            # regenera o cliente TypeScript a partir do OpenAPI
```

Os testes de pipeline/API criam o schema em `POLITEIA_TEST_DATABASE_URL`
(padrão `postgresql+psycopg://politeia:politeia@localhost:5432/politeia_test`; crie com
`docker exec <container> psql -U politeia -c "create database politeia_test"`).

## Dados reais importados (12/11/2026)

| Instituição | Membros em exercício | Proposições | Eventos de tramitação | Histórico partidário |
|---|---|---|---|---|
| Senado Federal | 81 (70 titulares, 11 suplentes) | 164 (PL, PLP, PEC, PDL, PRS dos últimos 45 dias) | 434 | sim (filiações oficiais) |
| ALEPE | 49 | 658 (projetos de 2026) | indisponível na fonte | indisponível na fonte |

## Limitações conhecidas

- **ALEPE sem identificador oficial de parlamentar:** a identidade é derivada do nome normalizado e marcada como
  `name-derived`; autores de proposições são ligados a pessoas apenas por correspondência exata de nome (`extracted`).
- **ALEPE sem datas de mandato, histórico partidário e tramitação** nos endpoints usados; a interface mostra essas
  capacidades como "indisponível na fonte" em vez de inventar dados.
- **Número oficial de assentos da ALEPE não verificado** em fonte oficial; a composição mostra apenas membros observados.
- **Senado:** proposições limitadas a uma janela de 45 dias e 400 detalhes por execução; comissões e votações planejadas.
- RLS ativado em todas as tabelas, sem políticas: no Supabase a Data API não lê nem grava nada; só o engine acessa
  (o advisor `rls_enabled_no_policy`, nível INFO, é esperado).

## Adicionando uma terceira instituição

Veja [docs/architecture.md](docs/architecture.md#adicionando-uma-instituição): basta um `pack.json` novo e, se a fonte
tiver formato próprio, um conector que produza os mesmos registros normalizados. Nem API nem interface mudam.
