# Relay do Senado

O acesso ao Senado é direto por padrão. Em ambientes que não alcançam os dois hosts oficiais,
`SENADO_PROXY_URL` (endpoint HTTPS) e `SENADO_PROXY_SECRET` podem habilitar este relay autenticado.
O Worker usa o mesmo segredo, fornecido somente como secret de runtime. Só Dados Abertos e Agência Senado
passam pelo relay; o restante dos feeds continua direto e as evidências mantêm o URL oficial.

Verificação local: `node --test workers/senado-proxy/worker.test.mjs`.
