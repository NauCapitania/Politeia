# Plataforma modular

As instituições e as análises são espaços independentes. `src/platform.ts` centraliza os destinos e as abas por poder; `src/analyses.ts` registra os recortes analíticos. O caso Master usa o dossiê existente, sem transformar o cadastro do Supremo em um caso específico.

`src/views/InstitutionModules.tsx` integra os módulos pelas exportações nomeadas `Camara`, `Executivo` e `Partidos`, nos respectivos arquivos de `src/views/`, sem props obrigatórias. Antes de cada módulo ser entregue, o destino mostra explicitamente a lacuna de cobertura; o build continua independente. Cada módulo deve tratar seus próprios estados de coleta, erro e ausência de dados, sem reutilizar o identificador institucional do Senado.

Os cadernos em **Análises → Nova análise** guardam pergunta e notas apenas no `localStorage` deste navegador (`politeia.analises.v1`). Abas deste navegador veem alterações, mas não há sincronização entre dispositivos ou coleta automática. **Investigar com o agente** acrescenta uma pergunta ao rascunho para revisão antes do envio; título e notas privados não entram no contexto oculto do agente.

# Snapshot estático e Cloudflare Pages

O terminal usa a API por padrão. Em `VITE_DATA_MODE=static`, lê o snapshot JSON de `public/data/`
e mostra no topo a data da exportação no horário de Brasília. O histórico estático inclui
1º/02/2023, a eleição da Mesa de 2025, as datas de mudanças observadas e o dia da exportação.

Na raiz do repositório, com `POLITEIA_DATABASE_URL` configurada apenas no ambiente do exportador
(ou no `.env` local), gere e confira o site sem iniciar a API:

```sh
uv run python -m scripts.export_snapshot
npm --prefix apps/terminal run build:static
npm --prefix apps/terminal run preview
```

Os arquivos do snapshot são gerados a cada deploy e não entram no Git. O exportador usa apenas
rotas de leitura e não roda migrações. A versão pública mantém as fontes e os status de ingestão,
sem publicar cabeçalhos das respostas de origem nem mensagens internas de erro.
`SNAPSHOT_WORKERS` limita o número de requisições e conexões simultâneas (padrão: 4).
Se o banco limitar conexões, experimente `SNAPSHOT_WORKERS=1`.

Com os secrets `CLOUDFLARE_API_TOKEN` (Pages:Edit) e `CLOUDFLARE_ACCOUNT_ID` no ambiente, rode
`npm --prefix apps/terminal run deploy:pages` para exportar, compilar e publicar no projeto
`politeia`. No primeiro deploy, vincule `politeia.pedropcventura.com` como domínio personalizado
no Cloudflare Pages. A publicação está protegida pelo Cloudflare Access; confirme o deploy pela API do Pages quando não houver sessão autenticada no domínio.

# Agente e desenvolvimento

`functions/api/agente.ts` atende `/api/agente` com Gemini e verifica a identidade do Cloudflare Access.
No Pages, configure `GEMINI_API_KEY`, `ACCESS_TEAM_DOMAIN`, `ACCESS_AUD` e `ACCESS_ALLOWED_EMAILS`
(lista separada por vírgulas), nos ambientes de produção e preview. Sem configuração válida, a função
nega acesso; nenhum segredo deve usar o prefixo `VITE_`.

Para testar localmente a Function depois do build estático, **neste diretório**:

```sh
npx wrangler pages dev dist --port 8788 --binding AGENTE_DEV_SEM_ACCESS=1
```

A exceção de Access funciona somente com hostname `localhost`; nunca a configure na publicação.
Forneça a chave Gemini apenas ao ambiente local do Wrangler. A UI em Vite, sozinha, não executa a Pages Function.

Publique deste diretório para o Wrangler incluir `functions/`:

```sh
npx wrangler pages deploy dist --project-name politeia --branch main
```

Validação: `npm test`, `npm run lint`, `npm run build` (API) ou `npm run build:static` (snapshot).
O roteiro completo de coleta, atualização e publicação está no [README principal](../../README.md).
