# Politeia

Monitor pessoal do **Senado Federal**: composição ao longo do tempo, perfis de senadores, votações, discursos,
notícias, a eleição da Presidência do Senado (2025 e 2027) e o acompanhamento do **STF e do caso Master** —
com foco em pedidos de impeachment de ministros do Supremo.

Princípios:
- **Fonte oficial primeiro.** Cada resposta das APIs do Senado é guardada intacta (URL, horário, SHA-256) antes da normalização.
- **Tempo é dado de primeira classe.** Mandatos, exercícios e filiações têm datas; a composição é reconstruída para qualquer dia.
- **Natureza da informação explícita.** Fato oficial, declaração, reportagem e análise/inferência são marcados separadamente.
  Menção em relatório ou reportagem não é prova de ilícito; ausência de declaração não é oposição.
- **Sem APIs pagas** nesta versão. Notícias vêm de RSS públicos; guardamos só título, link, data e um trecho curto.

## O que existe

| Aba | Conteúdo | Origem |
|---|---|---|
| Senado | Hemiciclo das 81 cadeiras com *slider* de data (desde 1º/02/2023), suplentes em exercício, trocas de partido | Dados Abertos: listas por legislatura, `/senador/{cod}/mandatos`, `/filiacoes` |
| Perfil | Mandatos, exercícios, histórico partidário, votos, discursos, notícias, posições com fonte | Dados Abertos + RSS + dossiês |
| Votações | Votações nominais de plenário desde 2025, voto a voto; secretas sinalizadas | `/votacao` |
| Presidência 2025 | Placar oficial 73/4/4, apoio partidário × cadeiras, probabilidade estimada por senador com justificativa | Dossiê curado + modelo |
| Presidência 2027 | Candidatos potenciais, posição sobre impeachment, cenários de votos (intervalos), composições projetadas divergentes | Dossiê curado |
| STF e caso Master | 11 cadeiras (10 ministros + vaga de Barroso), status dos relatórios da PF, prazo da PGR, quem decide o quê, rito do impeachment, linha do tempo | Dossiê curado + RSS |
| Notícias | Agência Senado, g1, Folha, Estadão, Poder360, Gazeta do Povo, Metrópoles, Agência Brasil, CartaCapital e buscas do Google Notícias | RSS |

### Voto secreto de 2025

Não existe registro oficial de quem votou em quem. O Politeia atribui a cada senador uma probabilidade *a priori*
(apoio declarado do partido, afinidade com candidaturas de oposição, autovoto, declarações públicas com fonte) e a
**condiciona exatamente ao placar oficial** por programação dinâmica (`engine/analysis/secret_ballot.py`): a soma das
probabilidades reproduz 73/4/4. Os parâmetros são hipóteses explícitas e aparecem na interface como “Hipótese”.

### Dossiês curados

`dossiers/*.json` guarda o que não está em API oficial (resultado da eleição em cédula, apoios partidários, status
na PGR, linha do tempo do caso Master). Todo item precisa de fonte; o carregador rejeita itens sem fonte.
Atualize o JSON e rode `python -m engine.cli dossiers`.

## Arquitetura

```
connectors/base        protocolo comum, cliente HTTP (rate limit, retries, hosts permitidos), contratos
connectors/senate      Dados Abertos do Senado: composition, members, votes, speeches, proposals
connectors/news        RSS público, ligação conservadora por nome completo
institution-packs/     configuração declarativa do Senado (fontes, feeds, capacidades)
engine/                ingestão, modelo de domínio (SQLAlchemy + Alembic), análises, API FastAPI
dossiers/              fatos e alegações curados com fontes
apps/terminal          interface React 19 + Vite + Blueprint, em português
```

Pipeline: conector → evidência bruta → registros normalizados → resolução de identidade → relações datadas → API → interface.

## Como rodar

Pré-requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, Docker.

```bash
docker compose -f infra/docker-compose.yml up -d   # ou POLITEIA_DATABASE_URL apontando para o Supabase
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m engine.cli sync                   # composition, members, votes, speeches, proposals, news
uv run python -m engine.cli dossiers               # dossiês curados + ligação de notícias
uv run uvicorn engine.api.app:app --port 8000      # OpenAPI em http://localhost:8000/docs

cd apps/terminal && npm install && npm run dev     # http://localhost:5173 (proxy /v1 -> :8000)
```

Escopos isolados: `uv run python -m engine.cli sync --scope news` (notícias a cada execução) ou `--scope votes`.

Testes: `uv run pytest`, `uv run ruff check .`, `cd apps/terminal && npm test && npm run build`.
Os testes de pipeline/API usam `POLITEIA_TEST_DATABASE_URL`
(padrão `postgresql+psycopg://politeia:politeia@localhost:5432/politeia_test`).

## Limitações conhecidas

- **Redes sociais:** sem API gratuita para leitura automática (X e Meta são pagas ou restritas); o perfil liga para a página
  oficial do senador, que lista as redes.
- **Comissões** ainda não são ingeridas (o endpoint testado mudou de rota).
- **Notícias** ligam senadores/ministros só por nome completo exato; apelidos e sobrenomes isolados ficam sem ligação.
- **Cenários de 2027** são intervalos derivados de contagens divulgadas por aliados e imprensa, não previsão.
- **Dossiês** são curadoria manual datada (`as_of`) e precisam ser atualizados conforme o caso evolui.
