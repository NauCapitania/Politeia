# Plataforma modular

As instituições e as análises são espaços independentes. `src/platform.ts` centraliza os destinos e as abas por poder; `src/analyses.ts` registra os recortes analíticos. O caso Master usa o dossiê existente, sem transformar o cadastro do Supremo em um caso específico.

`src/views/InstitutionModules.tsx` integra os módulos pelas exportações nomeadas `Camara`, `Executivo` e `Partidos`, nos respectivos arquivos de `src/views/`, sem props obrigatórias. Antes de cada módulo ser entregue, o destino mostra explicitamente a lacuna de cobertura; o build continua independente. Cada módulo deve tratar seus próprios estados de coleta, erro e ausência de dados, sem reutilizar o identificador institucional do Senado.

Os cadernos em **Análises → Nova análise** guardam pergunta e notas apenas no `localStorage` deste navegador (`politeia.analises.v1`). Não há sincronização ou coleta automática. **Investigar com o agente** prepara uma pergunta para revisão antes do envio; notas não são enviadas automaticamente.

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
no Cloudflare Pages. O site é público, sem Cloudflare Access.

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
