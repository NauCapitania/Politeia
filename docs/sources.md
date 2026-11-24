# Source inventory

Verified on 2026-11-12 against live endpoints. Nothing below is assumed from old examples.

## Senado Federal — `https://legis.senado.leg.br/dadosabertos`

OpenAPI: `/dadosabertos/v3/api-docs` (title "Dados Abertos Legislativos do Senado Federal e Congresso Nacional", v4.1.3.113). No authentication. Format selected by `Accept: application/json` (or `.json` suffix); XML and CSV also available on many services.

**Rate limiting (documented):** more than 10 req/s may get HTTP 429; 503 under heavy load; avoid round-clock bursts. Deprecated services return `Deprecation`, `Sunset` and `Link: <successor>; rel="successor"` headers.

| Endpoint | Status | Format | Used for | Important fields |
|---|---|---|---|---|
| `GET /senador/lista/atual` | active | JSON | Members (in exercise) | `IdentificacaoParlamentar.CodigoParlamentar` (stable ID), `NomeParlamentar`, `NomeCompletoParlamentar`, `SiglaPartidoParlamentar`, `UfParlamentar`, `UrlFotoParlamentar`, `UrlPaginaParlamentar`, `Bloco`, `Mandato.CodigoMandato`, `Mandato.DescricaoParticipacao` (Titular / 1º Suplente), `Mandato.PrimeiraLegislaturaDoMandato`/`SegundaLegislaturaDoMandato` (dates), `Mandato.Exercicios` |
| `GET /senador/{codigo}/filiacoes` | active | JSON | Party membership history | `Partido.CodigoPartido`, `SiglaPartido`, `NomePartido`, `DataFiliacao`, `DataDesfiliacao` |
| `GET /processo` | active | JSON (list) | Legislative proposals | `id`, `identificacao` ("PL 123/2026"), `tipoDocumento`, `ementa`, `dataApresentacao`, `situacaoAtual`, `tramitando`, `autoria` (free text only), `urlDocumento`. At least one filter required; date windows max 1 year |
| `GET /processo/{id}` | active | JSON | Proposal detail, authors, events | `autoriaIniciativa[].codigoParlamentar` (structured authors), `autuacoes[].situacoes[]`, `autuacoes[].informesLegislativos[]` (dated procedural records) |
| `/senador/{codigo}/autorias`, `/relatorias`, `/votacoes`, `/liderancas`, `/composicao/lista/lideranca*` | **deprecated** | — | not used | successors listed in the OpenAPI |
| `/composicao/lista/blocos`, `/composicao/lideranca`, `/senador/{codigo}/comissoes` | active | JSON | not yet ingested (Priority 2) | |

Observed on 2026-11-12: 81 senators in exercise (70 "Titular", 11 "1º Suplente" exercising the mandate).

**Limitations:** the `/processo` list has authors only as free text; structured authors need one `/processo/{id}` call per proposal. Seat count (81) is not in the API; it comes from the Constitution (art. 46, §1º — 3 per state × 26 states + DF).

Additional Senate endpoints (verified 2026-11-23):

| Endpoint | Used for |
|---|---|
| `GET /senador/lista/legislatura/{57,58}` | everyone who held or exercised a seat since 2023 |
| `GET /senador/{codigo}/mandatos` | mandates, `Exercicios` (start/end/cause) and substitutes → composition on any date |
| `GET /votacao?dataInicio&dataFim` | plenary roll calls with `votos[]`; `votacaoSecreta = "S"` marks secret ballots (only "Votou") |
| `GET /senador/{codigo}/discursos?dataInicio&dataFim` | speeches (summary, indexing, text URL) |

`/votacao/orientacaoBancada/{data}` returned 404; committee routes returned 301 and are not ingested yet.

## News — public RSS

Agência Senado, g1 Política, Folha Poder, Estadão Política, Poder360, Gazeta do Povo República, Metrópoles,
Agência Brasil Política, CartaCapital Política (HTTP 200 on 2026-11-23) plus three Google News RSS searches
(impeachment de ministro do STF, Banco Master e STF, eleição da Presidência do Senado 2027).
CNN Brasil, O Globo and R7 feeds tested returned 4xx. Only title, link, date, outlet and a ≤320-char excerpt are stored.

## Connector strategy

- One connector per source system, same protocol (`discover → fetch → normalize → validate → sync`).
- Shared HTTP client: timeouts, per-source rate limit (Senate ≤ 5 req/s), bounded retries with exponential backoff + jitter on 429/500/502/503/504 and network errors, `Retry-After` honored, deprecation headers logged.
- Every response is stored as a raw record (URL, status, format, retrieval time, SHA-256, payload, parser version) before normalization.
- Senate proposals: list window of recent proposals for the main types (PL, PLP, PEC, PDL, PRS), then detail per proposal for structured authors and events.
