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

## ALEPE — `https://dadosabertos.alepe.pe.gov.br/api/v1/`

Portal: `https://dadosabertos.alepe.pe.gov.br/` (own API, not SAPL). No authentication. No documented rate limit.

| Endpoint | Format | Used for | Important fields |
|---|---|---|---|
| `GET /parlamentares/` (trailing slash; without it → 301) | JSON (default) / CSV (`formato=csv`) | Members | `nomeParlamentar`, `partido` — **only these two fields**. Docs mention e-mail, response does not include it |
| `GET /proposicoes/projetos/` | XML (default) / CSV | Proposals (list) | `projeto@docid`, `numero`, `ano`, `legislatura`, `tipo`, `subtipo`, `ementa`, `dataPublicacao` (dd/mm/yyyy), `autores/autor@nome`, `autor@tipo` (DEPUTADO / EXTERNO / COMISSAO). Defaults to current year; filters `ano`, `legislatura` |
| `GET /proposicoes/projetos/?numero=N&ano=Y` | XML | Proposal detail | full text (`materia`, `materiaHtml`); no status, no procedural history observed |
| `/proposicoes/indicacoes/`, `/proposicoes/requerimentos/` | XML | not yet ingested | |
| `/servidores`, `/cargos`, `/lotacoes`, `/remuneracao`, `/contratos`, `/licitacoes` | JSON/CSV | not ingested (staff/financial data; out of scope, personal data) | |

Observed on 2026-11-12: 49 members; 658 projects for 2026 (549 PLO, 95 PR, 7 PLC, 4 PEC, 1 LDO, 1 PPA, 1 LOA); `docid` unique; (tipo, numero, ano) unique in the sample.

**Limitations (made visible in Politeia):**
- No official member identifier. Politeia derives a source key from the normalized parliamentary name and marks it as `name-derived`.
- No mandate dates, no party history, no photos, no committees, no votes, no procedural history, no current status for proposals.
- Proposal authors are names only; linking to members is a name match inside the same institution, recorded as `extracted` (not `verified`), and unmatched authors stay unresolved.
- Official seat count is not published by the API; it is left unverified.

## Connector strategy

- One connector per source system, same protocol (`discover → fetch → normalize → validate → sync`).
- Shared HTTP client: timeouts, per-source rate limit (Senate ≤ 5 req/s), bounded retries with exponential backoff + jitter on 429/500/502/503/504 and network errors, `Retry-After` honored, deprecation headers logged.
- Every response is stored as a raw record (URL, status, format, retrieval time, SHA-256, payload, parser version) before normalization.
- Senate proposals: list window of recent proposals for the main types (PL, PLP, PEC, PDL, PRS), then detail per proposal for structured authors and events.
- ALEPE proposals: current-year list (summary fields only).
