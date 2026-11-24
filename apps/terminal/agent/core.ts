import { SYSTEM_PROMPT } from './catalog'

export type ChatMessage = { papel: 'usuario' | 'agente'; texto: string }
export type ChartSpec = {
  tipo: 'barra' | 'linha' | 'pizza'
  titulo: string
  rotulos: string[]
  series: { nome: string; valores: number[] }[]
  unidade?: string
  nota?: string
}
export type NetworkSpec = {
  titulo: string
  nos: { id: string; rotulo: string; grupo?: string; peso?: number }[]
  arestas: { origem: string; destino: string; rotulo?: string; peso?: number }[]
  nota?: string
}
export type AgentEvent =
  | { tipo: 'passo'; texto: string }
  | { tipo: 'grafico'; grafico: ChartSpec }
  | { tipo: 'rede'; rede: NetworkSpec }
  | { tipo: 'resposta'; texto: string; modelo: string }
  | { tipo: 'erro'; texto: string }

type Part = Record<string, unknown> & { text?: string; thought?: boolean; functionCall?: { name: string; args?: Record<string, unknown>; id?: string } }
type Content = { role: 'user' | 'model'; parts: Part[] }

export type AgentDeps = {
  apiKey: string
  models: string[]
  readData: (path: string) => Promise<string | null>
  searchNews: (query: string) => Promise<NewsItem[]>
  fetchImpl?: typeof fetch
  signal?: AbortSignal
}
export type NewsItem = { titulo: string; link: string; data: string; veiculo: string }

const MAX_STEPS = 8
const MAX_TOOL_CHARS = 40_000
const MAX_HISTORY = 20
const TIME_BUDGET_MS = 75_000
const GEMINI = 'https://generativelanguage.googleapis.com/v1beta/models'

const TOOLS = [{
  functionDeclarations: [
    {
      name: 'ler_dados',
      description: 'Lê um arquivo JSON do snapshot do Politeia (Senado, STF, caso Master, notícias). Veja o catálogo nas instruções.',
      parameters: {
        type: 'object',
        properties: {
          caminho: { type: 'string', description: 'Ex.: /senado/composicao/2026-11-24 ou /senadores/per_xxx' },
          inicio: { type: 'number', description: 'Posição (em caracteres) para continuar um arquivo grande; use o valor de "proximo_inicio" da leitura anterior.' },
        },
        required: ['caminho'],
      },
    },
    {
      name: 'buscar_noticias',
      description: 'Pesquisa notícias recentes no Google Notícias (Brasil, pt-BR). Retorna título, veículo, data e link.',
      parameters: { type: 'object', properties: { consulta: { type: 'string' } }, required: ['consulta'] },
    },
    {
      name: 'mostrar_grafico',
      description: 'Mostra um gráfico ao Pedro na janela do agente. Use dados reais lidos nas outras ferramentas.',
      parameters: {
        type: 'object',
        properties: {
          tipo: { type: 'string', enum: ['barra', 'linha', 'pizza'] },
          titulo: { type: 'string' },
          rotulos: { type: 'array', items: { type: 'string' } },
          series: {
            type: 'array',
            items: { type: 'object', properties: { nome: { type: 'string' }, valores: { type: 'array', items: { type: 'number' } } }, required: ['nome', 'valores'] },
          },
          unidade: { type: 'string', description: 'Ex.: %, votos, senadores' },
          nota: { type: 'string', description: 'Fonte ou ressalva (ex.: "Inferência do modelo")' },
        },
        required: ['tipo', 'titulo', 'rotulos', 'series'],
      },
    },
    {
      name: 'mostrar_rede',
      description: 'Mostra uma rede de conexões (grafo) ao Pedro: senadores, partidos, blocos, comissões, votações, ministros, investigados, notícias. Use dados reais; cada aresta é uma relação concreta.',
      parameters: {
        type: 'object',
        properties: {
          titulo: { type: 'string' },
          nos: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                id: { type: 'string' },
                rotulo: { type: 'string' },
                grupo: { type: 'string', description: 'Categoria usada na cor (ex.: partido, "Notícia", "STF")' },
                peso: { type: 'number', description: 'Importância relativa (1 a 10)' },
              },
              required: ['id', 'rotulo'],
            },
          },
          arestas: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                origem: { type: 'string' },
                destino: { type: 'string' },
                rotulo: { type: 'string', description: 'Natureza da relação (ex.: "mesmo partido", "citado na reportagem")' },
                peso: { type: 'number' },
              },
              required: ['origem', 'destino'],
            },
          },
          nota: { type: 'string', description: 'Fonte ou ressalva' },
        },
        required: ['titulo', 'nos', 'arestas'],
      },
    },
  ],
}]

export const DATA_PATH = /^\/[a-z0-9_-]+(\/[a-z0-9_.-]+)*$/i

export function validChart(value: unknown): ChartSpec | null {
  const c = value as Partial<ChartSpec> | null
  if (!c || !['barra', 'linha', 'pizza'].includes(c.tipo as string) || typeof c.titulo !== 'string') return null
  if (!Array.isArray(c.rotulos) || !Array.isArray(c.series) || !c.rotulos.length || c.rotulos.length > 60) return null
  const rotulos = c.rotulos.map(String)
  const series = c.series.slice(0, c.tipo === 'pizza' ? 1 : 6).map((s) => ({
    nome: String(s?.nome ?? ''),
    valores: (Array.isArray(s?.valores) ? s.valores : []).slice(0, rotulos.length).map(Number),
  })).filter((s) => s.valores.length === rotulos.length && s.valores.every(Number.isFinite))
  if (!series.length) return null
  return { tipo: c.tipo!, titulo: c.titulo, rotulos, series, unidade: c.unidade ? String(c.unidade) : undefined, nota: c.nota ? String(c.nota) : undefined }
}

const MAX_NODES = 150
const MAX_EDGES = 400

export function validNetwork(value: unknown): NetworkSpec | null {
  const r = value as Partial<NetworkSpec> | null
  if (!r || typeof r.titulo !== 'string' || !Array.isArray(r.nos) || !Array.isArray(r.arestas)) return null
  const seen = new Set<string>()
  const nos = r.nos.slice(0, MAX_NODES).flatMap((n) => {
    const id = String(n?.id ?? '')
    if (!id || seen.has(id)) return []
    seen.add(id)
    const peso = Number(n.peso)
    return [{ id, rotulo: String(n.rotulo ?? id).slice(0, 60), grupo: n.grupo ? String(n.grupo).slice(0, 40) : undefined, peso: Number.isFinite(peso) ? Math.min(10, Math.max(1, peso)) : undefined }]
  })
  const arestas = r.arestas.slice(0, MAX_EDGES).flatMap((a) => {
    const origem = String(a?.origem ?? '')
    const destino = String(a?.destino ?? '')
    if (!seen.has(origem) || !seen.has(destino) || origem === destino) return []
    const peso = Number(a.peso)
    return [{ origem, destino, rotulo: a.rotulo ? String(a.rotulo).slice(0, 60) : undefined, peso: Number.isFinite(peso) ? Math.min(10, Math.max(1, peso)) : undefined }]
  })
  if (nos.length < 2) return null
  return { titulo: r.titulo, nos, arestas, nota: r.nota ? String(r.nota) : undefined }
}

export function contextLine(contexto?: { tela?: string; selecionado?: string | null }) {
  if (!contexto?.tela) return ''
  return `\n\nContexto da interface: o Pedro está na tela "${contexto.tela}"${contexto.selecionado ? `, com "${contexto.selecionado}" selecionado` : ''}.`
}

function toContents(messages: ChatMessage[]): Content[] {
  return messages.slice(-MAX_HISTORY).map((m) => ({ role: m.papel === 'usuario' ? 'user' : 'model', parts: [{ text: m.texto.slice(0, 8000) }] }))
}

export class GeminiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function generate(deps: AgentDeps, model: string, system: string, contents: Content[], final = false) {
  const res = await (deps.fetchImpl ?? fetch)(`${GEMINI}/${model}:generateContent`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-goog-api-key': deps.apiKey },
    signal: deps.signal,
    body: JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents, tools: TOOLS, ...(final ? { toolConfig: { functionCallingConfig: { mode: 'NONE' } } } : {}), generationConfig: { temperature: 0.4 } }),
  })
  if (!res.ok) throw new GeminiError(res.status, `Gemini ${model} ${res.status}: ${(await res.text().catch(() => '')).slice(0, 300)}`)
  const data = await res.json() as { candidates?: { content?: Content; finishReason?: string }[] }
  return data.candidates?.[0]?.content ?? { role: 'model' as const, parts: [] }
}

async function generateWithFallback(deps: AgentDeps, state: { model: number }, system: string, contents: Content[], final = false) {
  for (;;) {
    try {
      return await generate(deps, deps.models[state.model], system, contents, final)
    } catch (error) {
      const retryable = error instanceof GeminiError && [429, 500, 503, 404].includes(error.status)
      if (!retryable || state.model >= deps.models.length - 1) throw error
      state.model += 1
    }
  }
}

const tally = (items: Record<string, unknown>[], key: string) =>
  Object.fromEntries(Object.entries(items.reduce<Record<string, number>>((acc, item) => {
    const k = String(item[key] ?? 'sem informação')
    acc[k] = (acc[k] ?? 0) + 1
    return acc
  }, {})).sort((a, b) => b[1] - a[1]))

export function summarize(text: string) {
  try {
    const seats = (JSON.parse(text) as { seats?: unknown }).seats
    if (!Array.isArray(seats) || !seats.length) return null
    const items = seats as Record<string, unknown>[]
    return { total: items.length, por_partido: tally(items, 'party'), por_uf: tally(items, 'uf'), por_participacao: tally(items, 'participation') }
  } catch {
    return null
  }
}

export function page(text: string, inicio = 0) {
  const start = Math.max(0, Math.min(text.length, Math.floor(inicio) || 0))
  const end = start + MAX_TOOL_CHARS
  if (start === 0 && end >= text.length) return { conteudo: text }
  return { conteudo: text.slice(start, end), total: text.length, ...(end < text.length ? { proximo_inicio: end } : {}) }
}

async function runTool(deps: AgentDeps, call: NonNullable<Part['functionCall']>, emit: (e: AgentEvent) => void): Promise<unknown> {
  const args = call.args ?? {}
  if (call.name === 'ler_dados') {
    const path = String(args.caminho ?? '').replace(/\.json$/, '')
    emit({ tipo: 'passo', texto: `Lendo ${path}` })
    if (!DATA_PATH.test(path) || path.includes('..')) return { erro: 'Caminho inválido.' }
    const body = await deps.readData(path)
    if (body === null) return { erro: `Arquivo ${path} não existe no snapshot.` }
    const resumo = Number(args.inicio ?? 0) ? null : summarize(body)
    return { ...(resumo ? { resumo } : {}), ...page(body, Number(args.inicio ?? 0)) }
  }
  if (call.name === 'buscar_noticias') {
    const query = String(args.consulta ?? '').slice(0, 200)
    emit({ tipo: 'passo', texto: `Pesquisando notícias: ${query}` })
    try {
      return { resultados: await deps.searchNews(query) }
    } catch {
      return { erro: 'Busca de notícias indisponível agora.' }
    }
  }
  if (call.name === 'mostrar_grafico') {
    const chart = validChart(args)
    if (!chart) return { erro: 'Gráfico inválido: rótulos e valores precisam ter o mesmo tamanho.' }
    emit({ tipo: 'passo', texto: `Desenhando gráfico: ${chart.titulo}` })
    emit({ tipo: 'grafico', grafico: chart })
    return { ok: true }
  }
  if (call.name === 'mostrar_rede') {
    const rede = validNetwork(args)
    if (!rede) return { erro: 'Rede inválida: precisa de ao menos 2 nós com id e arestas entre ids existentes.' }
    emit({ tipo: 'passo', texto: `Montando rede: ${rede.titulo}` })
    emit({ tipo: 'rede', rede })
    return { ok: true, nos: rede.nos.length, arestas: rede.arestas.length }
  }
  return { erro: `Ferramenta desconhecida: ${call.name}` }
}

export async function runAgent(
  deps: AgentDeps,
  messages: ChatMessage[],
  contexto: { tela?: string; selecionado?: string | null } | undefined,
  emit: (e: AgentEvent) => void,
  today = new Date(),
) {
  const date = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'full', timeZone: 'America/Sao_Paulo' }).format(today)
  const system = `${SYSTEM_PROMPT}\n\nHoje é ${date}.${contextLine(contexto)}`
  const contents = toContents(messages)
  const state = { model: 0 }
  const started = Date.now()
  emit({ tipo: 'passo', texto: 'Pensando' })
  for (let step = 0; step < MAX_STEPS; step++) {
    deps.signal?.throwIfAborted()
    const final = step === MAX_STEPS - 1 || Date.now() - started > TIME_BUDGET_MS
    if (final && step > 0) emit({ tipo: 'passo', texto: 'Escrevendo a resposta com o que já levantei' })
    const content = await generateWithFallback(deps, state, system, contents, final)
    const parts = content.parts ?? []
    contents.push({ role: 'model', parts })
    const calls = parts.filter((p) => p.functionCall).map((p) => p.functionCall!)
    if (!calls.length) {
      const text = parts.filter((p) => p.text && !p.thought).map((p) => p.text).join('').trim()
      emit({ tipo: 'resposta', texto: text || 'Não consegui formular uma resposta. Tente reformular a pergunta.', modelo: deps.models[state.model] })
      return
    }
    const responses: Part[] = []
    for (const call of calls) {
      const response = await runTool(deps, call, emit)
      responses.push({ functionResponse: { name: call.name, ...(call.id ? { id: call.id } : {}), response } })
    }
    contents.push({ role: 'user', parts: responses })
  }
  emit({ tipo: 'resposta', texto: 'Parei após muitas consultas sem concluir. Tente uma pergunta mais específica.', modelo: deps.models[state.model] })
}

export function parseNewsRss(xml: string, limit = 10): NewsItem[] {
  const items: NewsItem[] = []
  for (const match of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const tag = (name: string) => decode(match[1].match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`))?.[1] ?? '')
    const veiculo = tag('source')
    let titulo = tag('title')
    if (veiculo && titulo.endsWith(` - ${veiculo}`)) titulo = titulo.slice(0, -veiculo.length - 3)
    items.push({ titulo, link: tag('link'), data: brDate(tag('pubDate')), veiculo })
    if (items.length >= limit) break
  }
  return items
}

function brDate(pubDate: string) {
  const d = new Date(pubDate)
  if (Number.isNaN(d.getTime())) return pubDate
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(d)
}

function decode(text: string) {
  return text.replace(/^<!\[CDATA\[|\]\]>$/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim()
}

export async function searchGoogleNews(query: string, fetchImpl: typeof fetch = fetch) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419`
  const res = await fetchImpl(url, { headers: { 'user-agent': 'Politeia/1.0 (monitor pessoal)' } })
  if (!res.ok) throw new Error(`RSS ${res.status}`)
  return parseNewsRss(await res.text())
}
