import { runAgent, searchGoogleNews, type AgentEvent, type ChatMessage } from '../../agent/core'
import { verifyAccess } from '../../agent/access'

type Env = {
  ASSETS: { fetch: typeof fetch }
  GEMINI_API_KEY?: string
  GEMINI_MODELS?: string
  ACCESS_TEAM_DOMAIN?: string
  ACCESS_AUD?: string
  ACCESS_ALLOWED_EMAILS?: string
  AGENTE_DEV_SEM_ACCESS?: string
}

const DEFAULT_MODELS = 'gemini-3.5-flash,gemini-flash-latest,gemini-flash-lite-latest'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } })

async function authorized(request: Request, env: Env) {
  if (env.AGENTE_DEV_SEM_ACCESS === '1' && new URL(request.url).hostname === 'localhost') return true
  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return false
  const email = await verifyAccess(request.headers.get('cf-access-jwt-assertion'), {
    team: env.ACCESS_TEAM_DOMAIN,
    aud: env.ACCESS_AUD,
    allowedEmails: (env.ACCESS_ALLOWED_EMAILS ?? '').split(',').map((e) => e.trim().toLowerCase()).filter(Boolean),
  })
  return email !== null
}

function parseBody(value: unknown): { mensagens: ChatMessage[]; contexto?: { tela?: string; selecionado?: string | null } } | null {
  const body = value as { mensagens?: unknown; contexto?: { tela?: unknown; selecionado?: unknown } } | null
  if (!body || !Array.isArray(body.mensagens) || !body.mensagens.length) return null
  const mensagens = body.mensagens.filter((m): m is ChatMessage =>
    !!m && (m.papel === 'usuario' || m.papel === 'agente') && typeof m.texto === 'string' && m.texto.trim() !== '')
  if (!mensagens.length || mensagens.at(-1)!.papel !== 'usuario') return null
  const tela = typeof body.contexto?.tela === 'string' ? body.contexto.tela.slice(0, 80) : undefined
  const selecionado = typeof body.contexto?.selecionado === 'string' ? body.contexto.selecionado.slice(0, 80) : null
  return { mensagens, contexto: { tela, selecionado } }
}

export const onRequestPost = async ({ request, env, waitUntil }: { request: Request; env: Env; waitUntil: (p: Promise<unknown>) => void }) => {
  if (!(await authorized(request, env))) return json(403, { erro: 'Acesso não autorizado.' })
  if (!env.GEMINI_API_KEY) return json(503, { erro: 'O agente não está configurado (chave do Gemini ausente).' })
  const body = parseBody(await request.json().catch(() => null))
  if (!body) return json(400, { erro: 'Requisição inválida.' })

  const origin = new URL(request.url).origin
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>()
  const writer = writable.getWriter()
  const encoder = new TextEncoder()
  const stop = new AbortController()
  const emit = (event: AgentEvent) => { writer.write(encoder.encode(`${JSON.stringify(event)}\n`)).catch(() => stop.abort()) }

  const work = runAgent({
    apiKey: env.GEMINI_API_KEY,
    models: (env.GEMINI_MODELS ?? DEFAULT_MODELS).split(',').map((m) => m.trim()).filter(Boolean),
    readData: async (path) => {
      const res = await env.ASSETS.fetch(new Request(`${origin}/data${path}.json`))
      if (!res.ok || !res.headers.get('content-type')?.includes('json')) return null
      return res.text()
    },
    searchNews: (query) => searchGoogleNews(query),
    signal: stop.signal,
  }, body.mensagens, body.contexto, emit)
    .catch((error: unknown) => {
      if (stop.signal.aborted) return
      const status = (error as { status?: number }).status
      emit({ tipo: 'erro', texto: status === 429
        ? 'Limite gratuito do Gemini atingido no momento. Espere um minuto e tente de novo.'
        : 'O agente não conseguiu responder agora. Tente de novo em instantes.' })
    })
    .finally(() => writer.close().catch(() => {}))

  waitUntil(work)
  return new Response(readable, {
    headers: { 'content-type': 'application/x-ndjson; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' },
  })
}

export const onRequest = () => json(405, { erro: 'Use POST.' })
