import type { AgentEvent, ChatMessage } from '../../agent/core'

export type { AgentEvent, ChartSpec, ChatMessage, NetworkSpec } from '../../agent/core'

export async function askAgent(
  mensagens: ChatMessage[],
  contexto: { tela: string; selecionado: string | null },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
) {
  const res = await fetch('/api/agente', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ mensagens, contexto }), signal,
  })
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null) as { erro?: string } | null
    onEvent({ tipo: 'erro', texto: body?.erro ?? (res.status === 404 ? 'O agente só funciona no site publicado (Cloudflare Pages).' : `Erro ${res.status}`) })
    return
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (value) buffer += value
    const lines = buffer.split('\n')
    buffer = done ? '' : lines.pop()!
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as AgentEvent)
    if (done) return
  }
}
