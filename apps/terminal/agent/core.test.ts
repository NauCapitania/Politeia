import { describe, expect, it, vi } from 'vitest'
import { parseNewsRss, runAgent, validChart, validNetwork, type AgentEvent } from './core'

const reply = (parts: unknown[]) => new Response(JSON.stringify({ candidates: [{ content: { role: 'model', parts } }] }))

describe('runAgent', () => {
  it('lê dados, desenha gráfico e responde, repassando as chamadas ao Gemini', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(reply([{ functionCall: { name: 'ler_dados', args: { caminho: '/senado/composicao/2026-11-24' }, id: 'a' }, thoughtSignature: 'sig' }]))
      .mockResolvedValueOnce(reply([{ functionCall: { name: 'mostrar_grafico', args: { tipo: 'barra', titulo: 'Bancadas', rotulos: ['PL', 'PT'], series: [{ nome: 'Senadores', valores: [14, 9] }] } } }]))
      .mockResolvedValueOnce(reply([{ text: 'pensando', thought: true }, { text: 'O PL tem 14 senadores. [Fato oficial]' }]))
    const readData = vi.fn(async () => '{"seats":[]}')
    const events: AgentEvent[] = []
    await runAgent({ apiKey: 'k', models: ['m1'], readData, searchNews: vi.fn(), fetchImpl }, [{ papel: 'usuario', texto: 'Quantos?' }],
      { tela: 'Senado — composição' }, (e) => events.push(e))

    expect(readData).toHaveBeenCalledWith('/senado/composicao/2026-11-24')
    expect(events.at(-1)).toEqual({ tipo: 'resposta', texto: 'O PL tem 14 senadores. [Fato oficial]', modelo: 'm1' })
    expect(events.find((e) => e.tipo === 'grafico')).toMatchObject({ grafico: { titulo: 'Bancadas' } })
    const second = JSON.parse(fetchImpl.mock.calls[1][1].body)
    expect(second.contents[1].parts[0].thoughtSignature).toBe('sig')
    expect(second.contents[2].parts[0].functionResponse).toEqual({ name: 'ler_dados', id: 'a', response: { conteudo: '{"seats":[]}' } })
    expect(second.systemInstruction.parts[0].text).toContain('Senado — composição')
    expect(fetchImpl.mock.calls[0][1].headers['x-goog-api-key']).toBe('k')
  })

  it('troca de modelo quando a cota gratuita estoura', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 429 }))
      .mockResolvedValueOnce(reply([{ text: 'ok' }]))
    const events: AgentEvent[] = []
    await runAgent({ apiKey: 'k', models: ['m1', 'm2'], readData: vi.fn(), searchNews: vi.fn(), fetchImpl }, [{ papel: 'usuario', texto: 'oi' }], undefined, (e) => events.push(e))
    expect(fetchImpl.mock.calls[1][0]).toContain('/m2:generateContent')
    expect(events.at(-1)).toMatchObject({ texto: 'ok', modelo: 'm2' })
  })

  it('recusa caminhos fora do snapshot', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(reply([{ functionCall: { name: 'ler_dados', args: { caminho: '/../segredo' } } }]))
      .mockResolvedValueOnce(reply([{ text: 'fim' }]))
    const readData = vi.fn()
    await runAgent({ apiKey: 'k', models: ['m'], readData, searchNews: vi.fn(), fetchImpl }, [{ papel: 'usuario', texto: 'x' }], undefined, () => {})
    expect(readData).not.toHaveBeenCalled()
    expect(JSON.parse(fetchImpl.mock.calls[1][1].body).contents[2].parts[0].functionResponse.response).toEqual({ erro: 'Caminho inválido.' })
  })
})

describe('auxiliares', () => {
  it('valida gráficos', () => {
    expect(validChart({ tipo: 'barra', titulo: 't', rotulos: ['a', 'b'], series: [{ nome: 's', valores: [1] }] })).toBeNull()
    expect(validChart({ tipo: 'pizza', titulo: 't', rotulos: ['a'], series: [{ nome: 's', valores: ['2'] }] })?.series[0].valores).toEqual([2])
  })

  it('lê o RSS do Google Notícias', () => {
    const xml = '<rss><channel><item><title>PGR analisa caso Master - Folha</title><link>https://n/1</link><pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate><source url="https://folha">Folha</source></item></channel></rss>'
    expect(parseNewsRss(xml)).toEqual([{ titulo: 'PGR analisa caso Master', link: 'https://n/1', data: 'Mon, 23 Nov 2026 10:00:00 GMT', veiculo: 'Folha' }])
  })
})

describe('validNetwork', () => {
  it('descarta arestas para nós inexistentes e nós duplicados', () => {
    const rede = validNetwork({
      titulo: 'Rede',
      nos: [{ id: 'a', rotulo: 'A', grupo: 'PL' }, { id: 'b', rotulo: 'B' }, { id: 'a', rotulo: 'A2' }],
      arestas: [{ origem: 'a', destino: 'b', rotulo: 'mesmo bloco' }, { origem: 'a', destino: 'x' }, { origem: 'b', destino: 'b' }],
    })
    expect(rede?.nos).toHaveLength(2)
    expect(rede?.arestas).toEqual([{ origem: 'a', destino: 'b', rotulo: 'mesmo bloco', peso: undefined }])
  })
  it('rejeita rede com menos de 2 nós', () => {
    expect(validNetwork({ titulo: 'x', nos: [{ id: 'a', rotulo: 'A' }], arestas: [] })).toBeNull()
  })
})
