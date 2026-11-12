# Arquitetura

Monólito modular: um processo de engine (FastAPI + CLI de ingestão) e uma aplicação web. Nada de filas, microserviços ou
grafos genéricos; relações são tabelas relacionais tipadas.

## Fluxo de dados

```
fonte oficial ──HTTP──▶ Connector.fetch ──▶ ingestion.raw_records (bytes/JSON, sha256, headers, URL)
                          │
                          ▼
                 Connector.normalize ──▶ registros neutros (PersonRecord, MandateRecord, ProposalRecord…)
                          │
                 Connector.validate  ──▶ ingestion.validation_issues
                          │ (erros ⇒ dados normalizados ficam intactos)
                          ▼
                 Persistor (upsert idempotente) ──▶ core.* / legislative.* + evidence.*
                          │
                 recompute_capabilities ──▶ registry.capability_states
                          │
                 engine/api (read-models Pydantic) ──▶ apps/terminal
```

## Conectores

Contrato (`connectors/base/protocol.py`): `discover()`, `fetch(scope)`, `normalize(batch)`, `validate(batch)`, `run()`.
Toda lógica específica de fonte (nomes de campos, XML, códigos de tipo, URLs oficiais) fica no conector.

`SourceHttpClient` (`connectors/base/http.py`): somente HTTPS, allow-list de hosts por fonte (inclusive em
redirecionamentos), limite de requisições por segundo do pack, até 4 tentativas com backoff exponencial + jitter em
429/5xx, respeito a `Retry-After`, preservação de `Deprecation`/`Sunset`/`Link`/`ETag`, SHA-256 do corpo.

## Armazenamento

| Schema | Conteúdo |
|---|---|
| `registry` | instituições, sistemas de origem, estados de capacidade |
| `ingestion` | execuções, raw records (únicos por fonte + URL + hash), problemas de validação |
| `core` | pessoas, identificadores externos, partidos, mandatos, filiações, comissões |
| `legislative` | proposições, autores, relatores, eventos |
| `evidence` | ligação entidade/relação ⇄ raw record + caminho (JSONPath/XPath) |

- IDs canônicos opacos (`per_…`, `man_…`, `pty_…`, `prp_…`) nunca derivados de nomes; IDs da fonte ficam em
  `core.external_identifiers` com `quality` (`official` ou `name-derived`).
- Tempo: mandatos e filiações têm `valid_from`/`valid_to`; tudo tem `first_seen_at`/`last_seen_at`. Quem some da lista
  completa de membros deixa de estar `in_exercise`, sem apagar histórico.
- Status epistêmico em relações e atributos: `verified`, `extracted`, `derived`, `conflicting`, `unknown`.
- RLS ativado em todas as tabelas sem políticas: no Supabase, nada fica exposto pela Data API; apenas o engine acessa.

## Capacidades

`engine/capabilities/compute.py` deriva o status de cada capacidade (membros, mandatos, composição, histórico,
proposições, autoria, tramitação, comissões, votações) a partir das execuções e dos dados efetivamente gravados:
`available`, `partial`, `empty`, `stale`, `ingestion_failed`, `not_ingested`, `unavailable_in_source`. A interface lê
esse estado; o pack apenas declara o que a fonte publica.

## API v1

`/v1/institutions`, `/{id}`, `/{id}/capabilities`, `/{id}/composition`, `/{id}/members`, `/{id}/proposals`,
`/{id}/proposal-types`, `/{id}/graph?focus=`, `/v1/entities/{id}`, `/relationships`, `/timeline`,
`/v1/sources/{raw_record_id}?path=`, `/v1/ingestion/status`. Coleções paginadas (`limit`, `offset`, `total`), cada fato
traz `sources` com URL oficial, data de coleta e hash. O cliente TypeScript é gerado do OpenAPI
(`apps/terminal/src/api/schema.d.ts`).

## Interface

Desktop-first: barra superior (instituição, busca, sincronização), navegação lateral com capacidades, canvas central e
inspetor à direita. Composição em hemiciclo com o número de assentos vindo da instituição; grafo radial centrado no
objeto selecionado, com arestas tipadas e explicadas; explorador de proposições com autoria, situação, tramitação e
link oficial; página de fontes e cobertura com execuções de ingestão.

## Adicionando uma instituição

1. Crie `institution-packs/<slug>/pack.json` (copie um existente): `institution` (nome, tipo, jurisdição, assentos com
   fonte, terminologia), `sources` (URL base, hosts permitidos, conector, rate limit, config) e `capabilities` esperadas.
2. Se a fonte tiver formato novo, implemente um `Connector` em `connectors/<nome>/` que produza os registros de
   `connectors/base/protocol.py`, registre-o em `engine/registry.py` (`CONNECTORS`) e grave fixtures em `tests/fixtures/`.
3. `uv run python -m engine.cli sync --institution <id>`. A API e a interface passam a exibir a instituição sem mudanças.
