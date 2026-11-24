# Politeia

Plataforma pessoal de **análises políticas do Brasil**, em português, com espaços independentes para
instituições, fontes e análises temáticas. Reúne Congresso Nacional, Senado, Câmara, Supremo Tribunal Federal,
Poder Executivo e partidos, com visualizações temporais e um agente para investigar o contexto disponível.

O **Caso Master** é uma análise em **Análises**, não o nome nem a definição do Supremo. Novos recortes podem
ser adicionados ao catálogo; cadernos pessoais permitem guardar perguntas e notas neste navegador.

Site: [politeia.pedropcventura.com](https://politeia.pedropcventura.com), protegido por Cloudflare Access.

Princípios:
- **Fonte oficial primeiro.** Respostas dos conectores são guardadas como evidências (URL, horário, SHA-256) antes da normalização.
- **Tempo é dado de primeira classe.** Mandatos, exercícios e filiações têm datas; a composição é reconstruída para qualquer dia.
- **Natureza da informação explícita.** Fato oficial, declaração, reportagem e análise/inferência são marcados separadamente.
  Menção em relatório ou reportagem não é prova de ilícito; ausência de declaração não é oposição.
- **Sem APIs pagas** nesta versão. Notícias vêm de RSS públicos; guardamos só título, link, data e um trecho curto.

## O que existe

| Aba | Conteúdo | Origem |
|---|---|---|
| Análises | Caso Master, Presidência do Senado em 2027, votações e cadernos pessoais; perguntas editáveis para o agente | Dossiês, dados institucionais e notas locais |
| Congresso Nacional | Relação entre Senado e Câmara, processo legislativo, competências e limites dos poderes | Guias com referências constitucionais |
| Senado | Hemiciclo das 81 cadeiras com *slider* de data (desde 1º/02/2023), suplentes em exercício, trocas de partido | Dados Abertos: listas por legislatura, `/senador/{cod}/mandatos`, `/filiacoes` |
| Perfil | Mandatos, exercícios, histórico partidário, votos, discursos, notícias, posições com fonte | Dados Abertos + RSS + dossiês |
| Votações | Votações nominais de plenário desde 2025, voto a voto; secretas sinalizadas | `/votacao` |
| Presidência 2025 | Placar oficial 73/4/4, apoio partidário × cadeiras, probabilidade estimada por senador com justificativa | Dossiê curado + modelo |
| Presidência 2027 | Candidatos potenciais, posição sobre impeachment, cenários de votos (intervalos), composições projetadas divergentes | Dossiê curado |
| Câmara dos Deputados | Composição, deputados, filiações, proposições, tramitações, votações e comissões | Dados Abertos da Câmara |
| Supremo Tribunal Federal | Competências, limites e relações institucionais; ligação para análises temáticas | Guias com fontes constitucionais |
| Caso Master (em Análises) | Composição do Supremo no recorte, relatórios da PF, situação da PGR, rito do impeachment e linha do tempo | Dossiê curado e datado + RSS |
| Poder Executivo | Estrutura de órgãos, ministérios e entidades vinculadas, titulares e linha do tempo do gabinete | SIORG + dossiê de titulares com fontes identificadas |
| Partidos e financiamento | Árvore de criação, fusões e incorporações, motivos declarados, Fundo Partidário e Fundo Eleitoral | Dossiê com fontes do TSE e referências históricas |
| Notícias | Agência Senado, g1, Folha, Estadão, Poder360, Gazeta do Povo, Metrópoles, Agência Brasil e buscas do Google Notícias (incluindo CartaCapital Política) | RSS |
| Fontes e cobertura | Evidências, capacidades e estado das coletas; lacunas explícitas | Registros de ingestão |

As guias explicam poderes e comissões; não substituem dados coletados. **Ausência de cobertura não significa
ausência de atividade.** A interface tem temas claro/escuro e navegação móvel; o Agente ocupa uma faixa própria
no celular para não cobrir o texto.

### Cadernos e agente

Os cadernos ficam no `localStorage` (`politeia.analises.v1`): não sincronizam entre dispositivos.
**Investigar com o agente** prepara um rascunho editável, sem enviar automaticamente. Título e notas privados
não entram no contexto oculto do agente. Perguntas acima de 8.000 caracteres permanecem visíveis, mas precisam
ser reduzidas antes do envio. Se o navegador não conseguir salvar, copie as notas antes de sair.

O agente usa `/api/agente`, uma Pages Function com Gemini, e recebe apenas o contexto explicitamente preparado
pela interface. A chave fica no servidor, nunca no bundle. Configuração e desenvolvimento em
[`apps/terminal/README.md`](apps/terminal/README.md).

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
connectors/chamber     Dados Abertos da Câmara: composição, deputados, proposições, votos e comissões
connectors/executive   estrutura do Executivo e titulares
connectors/news        RSS público, ligação conservadora por nome completo
institution-packs/     configuração declarativa por instituição (fontes, feeds, capacidades)
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
uv run python -m engine.cli sync                   # escopos suportados de todas as instituições registradas
uv run python -m engine.cli dossiers               # dossiês curados + ligação de notícias
uv run uvicorn engine.api.app:app --port 8000      # OpenAPI em http://localhost:8000/docs

cd apps/terminal && npm install && npm run dev     # http://localhost:5173 (proxy /v1 -> :8000)
```

Escopos isolados: `uv run python -m engine.cli sync --scope news` (notícias a cada execução) ou `--scope votes`.
Para selecionar uma instituição, use `--institution ins_br_senado`, `--institution ins_br_camara` ou
`--institution ins_br_executivo`. A Câmara inclui `committees`; o Executivo usa `structure` e `members`.

Para inspeção visual sem alterar o banco, uma base já preparada pode servir a API com `uvicorn`: não é preciso
rodar migrações ou `sync`. Outra opção é exportar o snapshot, compilar em modo estático e usar `npm run preview`
em `apps/terminal`; o exportador consulta apenas rotas de leitura.

Para reprocessar proposições sem consultar o Senado, use
`uv run python -m engine.cli replay-proposals --from-run UUID` com a última coleta utilizável (lote completo),
ou `uv run python -m engine.cli replay-proposals --proposal-id ID --proposal-id ID` com IDs oficiais do Senado
para selecionar os registros armazenados mais recentes de cada proposição. O run registra `stats.mode = replay`
e reutiliza as evidências originais, sem atualizar a data da última coleta da fonte.

Testes: `uv run pytest`, `uv run ruff check .`, `cd apps/terminal && npm test && npm run build`.
Os testes de pipeline/API usam `POLITEIA_TEST_DATABASE_URL`
(padrão `postgresql+psycopg://politeia:politeia@localhost:5432/politeia_test`).

## Atualização e publicação

1. Atualizar a `main` e instalar dependências quando necessário; aplicar migrações pendentes antes da coleta.
2. Coletar os escopos das instituições e RSS com `engine.cli sync`; carregar dossiês com `engine.cli dossiers`.
3. Conferir `/v1/ingestion/status` e **Fontes e cobertura**. Investigar estados `failed`/`partial`, sem tratá-los
   como coleta completa. Alterações dos dossiês passam por PR e preservam fontes, datas e tipo de informação.
4. Rodar testes/revisão, mesclar e exportar o snapshot da base de destino; compilar e publicar a `main`.

Com `POLITEIA_DATABASE_URL`, `CLOUDFLARE_ACCOUNT_ID` e `CLOUDFLARE_API_TOKEN` somente no ambiente:

```bash
SNAPSHOT_WORKERS=4 uv run python -m scripts.export_snapshot
npm --prefix apps/terminal run build:static
cd apps/terminal
npx wrangler pages deploy dist --project-name politeia --branch main
```

Publique **de `apps/terminal`**, onde fica `functions/`, para incluir `/api/agente`. A alternativa
`npm --prefix apps/terminal run deploy:pages` executa exportação, build e deploy; a sequência explícita acima
também fixa a branch de produção. Os JSONs gerados em `public/data/` não entram no Git, mantêm proveniência
e removem cabeçalhos de resposta e mensagens internas de erro. A interface mostra a data da exportação,
não uma garantia de que todas as fontes estejam atualizadas.

O domínio exige Cloudflare Access. Sem login, uma requisição ao site pode apenas redirecionar para autenticação;
confirme o deploy pela [API do Cloudflare Pages](https://developers.cloudflare.com/api/resources/pages/subresources/projects/subresources/deployments/methods/list/),
conferindo ambiente `production`, etapa `success` e commit da `main`. Não coloque credenciais de banco ou tokens
no repositório, no snapshot nem no front-end.

## Limitações conhecidas

- **Redes sociais:** sem API gratuita para leitura automática (X e Meta são pagas ou restritas); o perfil liga para a página
  oficial do senador, que lista as redes.
- **Comissões:** a Câmara tem ingestão própria; o Senado ainda não tem cobertura equivalente.
- **Executivo e partidos:** a estrutura SIORG é um recorte da coleta e históricos/fundos são datados; não
  representam todas as pessoas do governo nem todo o financiamento partidário desde a ditadura.
- **Histórico institucional:** o Supremo não tem conector geral de processos; o Caso Master é curadoria,
  não monitoramento completo do tribunal. Novas análises precisam declarar fontes e lacunas próprias.
- **Notícias** ligam senadores/ministros só por nome completo exato; apelidos e sobrenomes isolados ficam sem ligação.
- **Cenários de 2027** são intervalos derivados de contagens divulgadas por aliados e imprensa, não previsão.
- **Dossiês** são curadoria manual datada (`as_of`) e precisam ser atualizados conforme o caso evolui.
