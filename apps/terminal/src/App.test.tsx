import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { useStore } from './store'
import { hemicycleLayout } from './views/Hemicycle'

const inst = {
  id: 'ins_br_senado', slug: 'brazil-senate', official_name: 'Senado Federal', short_name: 'Senado', institution_type: 'chamber',
  jurisdiction: 'Federal', geographic_scope: 'Brasil', country: 'BR', website: 'https://www.senado.leg.br', seat_count: 81,
  seat_count_status: 'verified', seat_count_source: null, terminology: {}, observed_member_count: 81, pack_id: 'brazil-senate',
  pack_version: '0.2.0', last_ingested_at: '2026-11-24T00:00:00Z', sources: [{ id: 's', name: 'Dados Abertos', base_url: 'https://x', documentation_url: null }],
}
const seat = (i: number) => ({ person_id: `per_${i}`, code: String(i), name: `Senador ${i}`, uf: 'SP', party: i % 2 ? 'PL' : 'PT', participation: i === 3 ? 'suplente' : 'titular' })
const src = [{ url: 'https://www25.senado.leg.br/x', outlet: 'Senado', date: '2025-02-01', kind: 'official' }]
const posterior = { 'Davi Alcolumbre': 0.9, 'Astronauta Marcos Pontes': 0.05, 'Eduardo Girão': 0.05 }
const DATA: Record<string, unknown> = {
  '/v1/institutions': [inst],
  '/v1/institutions/ins_br_senado/capabilities': [{ capability: 'members', status: 'available', record_count: 81, coverage: {}, last_success_at: null, note: null, issues: [] }],
  '/v1/senado/composicao': { date: '2026-11-24', observed: 81, seats: Array.from({ length: 81 }, (_, i) => seat(i)) },
  '/v1/senado/mudancas': [],
  '/v1/senadores/per_1': {
    id: 'per_1', code: '1', name: 'Senador 1', full_name: 'Senador Um', photo_url: null, links: { perfil_oficial: 'https://www25.senado.leg.br/1' },
    social_note: 'nota', mandates: [{ id: 'm', uf: 'SP', participation: 'holder', start: '2023-02-01', end: '2031-01-31' }], exercises: [],
    parties: [{ party: 'PL', from: '2022-01-01', to: null, basis: 'affiliation_history' }], vote_summary: { Sim: 3 }, votes: [], speeches: [], news: [], claims: [],
  },
  '/v1/presidencia/2025': {
    available: true,
    contest: { title: 'Eleição para a Presidência do Senado (biênio 2025–2026)', note: 'O voto foi secreto.', result: [
      { candidate: 'Davi Alcolumbre', votes: 73, party: 'UNIÃO', uf: 'AP' }, { candidate: 'Astronauta Marcos Pontes', votes: 4, party: 'PL', uf: 'SP' },
      { candidate: 'Eduardo Girão', votes: 4, party: 'NOVO', uf: 'CE' }] },
    contest_sources: src, model: { method: 'Programação dinâmica', caveats: ['Hipótese'] }, model_sources: src,
    parties: [{ party: 'PL', senators: 14, support: { candidate: 'Davi Alcolumbre', support: 'declared' }, support_sources: src, expected_votes: posterior }],
    senators: Array.from({ length: 81 }, (_, i) => ({ ...seat(i), prior: posterior, posterior, most_likely: 'Davi Alcolumbre', justification: [{ kind: 'analysis', text: `Justificativa ${i}` }] })),
    summary: { declared_support_seats: 76, votes: { 'Davi Alcolumbre': 73 }, expected_check: { 'Davi Alcolumbre': 73, 'Astronauta Marcos Pontes': 4, 'Eduardo Girão': 4 } },
  },
}

function mockFetch() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(DATA[url.split('?')[0]] ?? []), { status: 200 })))
}
const renderApp = () => render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>)

beforeEach(() => {
  useStore.setState({ institutionId: null, view: 'senado', selectedId: null, partyFilter: null, search: '' })
  mockFetch()
})

describe('Snapshot estático', () => {
  it('mostra a data em BRT, carrega as cadeiras e filtra proposições sem a API', async () => {
    vi.stubEnv('VITE_DATA_MODE', 'static')
    const date = '2026-11-23'
    const snapshot: Record<string, unknown> = {
      '/data/meta.json': { generated_at: '2026-11-24T01:30:00Z', composition_dates: ['2023-02-01', date] },
      '/data/institutions.json': [inst],
      '/data/senado/mudancas.json': [],
      [`/data/senado/composicao/${date}.json`]: { date, observed: 1, seats: [seat(1)] },
      '/data/senado/composicao/2023-02-01.json': { date: '2023-02-01', observed: 1, seats: [seat(2)] },
      '/data/institutions/ins_br_senado/proposal-types.json': [
        { type_code: 'PL', type_name: 'Projeto de Lei', count: 51 },
        { type_code: 'PEC', type_name: 'Proposta de Emenda', count: 1 },
      ],
      '/data/institutions/ins_br_senado/proposals.json': [
        ...Array.from({ length: 50 }, (_, i) => ({ id: `prop_pl_${i}`, identifier: `PL ${i + 1}/2026`, type_code: 'PL', ementa: 'Crédito rural', authors: [] })),
        { id: 'prop_pl_50', identifier: 'PL 51/2026', type_code: 'PL', ementa: 'Crédito urbano', authors: [] },
        { id: 'prop_pec', identifier: 'PEC 1/2026', type_code: 'PEC', ementa: 'Crédito rural', authors: [] },
      ],
    }
    const fetchSnapshot = vi.fn(async (url: string) => new Response(JSON.stringify(snapshot[url]), {
      status: Object.hasOwn(snapshot, url) ? 200 : 404,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchSnapshot)
    try {
      renderApp()
      expect(await screen.findByText(/Último snapshot: 23\/11\/2026.*22:30 BRT/)).toBeInTheDocument()
      await waitFor(() => expect(screen.getByTestId('seat')).toHaveTextContent('Senador 1'))
      await userEvent.click(screen.getByText('1º/02/2023'))
      await waitFor(() => expect(screen.getByTestId('seat')).toHaveTextContent('Senador 2'))

      await userEvent.click(screen.getByRole('tab', { name: 'Proposições' }))
      await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Tipo' }), 'PL')
      await screen.findByText('1–50 de 51')
      await userEvent.click(screen.getByRole('button', { name: 'Próxima' }))
      expect(await screen.findByText('PL 51/2026')).toBeInTheDocument()
      const user = userEvent.setup()
      await user.click(screen.getByPlaceholderText('Ementa ou número…'))
      await user.paste('CRÉDITO URBANO')
      expect(await screen.findByText('1 registros ingeridos')).toBeInTheDocument()
      expect(screen.getByText('PL 51/2026')).toBeInTheDocument()
      expect(screen.queryByText('PEC 1/2026')).not.toBeInTheDocument()
      expect(fetchSnapshot.mock.calls.every(([url]) => url.startsWith('/data/'))).toBe(true)
      expect(fetchSnapshot.mock.calls.filter(([url]) => url.endsWith('/proposals.json'))).toHaveLength(1)
    } finally {
      vi.unstubAllEnvs()
      useStore.setState({ senadoTab: 'composicao' })
    }
  })
})

describe('hemicycleLayout', () => {
  it('places exactly one point per seat', () => {
    for (const n of [11, 49, 81, 513]) expect(hemicycleLayout(n, 600).points).toHaveLength(n)
  })
})

describe('Monitor do Senado', () => {
  it('desenha as 81 cadeiras e abre o perfil do senador', async () => {
    renderApp()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
    await userEvent.click(screen.getAllByTestId('seat').find((s) => s.textContent?.startsWith('Senador 1 '))!)
    expect(await screen.findByText('Senador Um')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Perfil oficial/ })).toHaveAttribute('href', 'https://www25.senado.leg.br/1')
  })

  it('mostra o voto secreto de 2025 como inferência com justificativa', async () => {
    renderApp()
    await userEvent.click(await screen.findByRole('tab', { name: /Presidência 2025/ }))
    expect(await screen.findByText(/O voto foi secreto/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
    await userEvent.click(screen.getAllByTestId('seat')[0])
    expect(await screen.findByText(/Justificativa/)).toBeInTheDocument()
    expect(screen.getAllByText('Hipótese').length).toBeGreaterThan(0)
  })
})

describe('Agente político', () => {
  it('abre a janela, mostra os passos, o gráfico e a resposta do agente', async () => {
    const lines = [
      { tipo: 'passo', texto: 'Lendo /senado/composicao/2026-11-24' },
      { tipo: 'grafico', grafico: { tipo: 'barra', titulo: 'Bancadas por partido', rotulos: ['PL', 'PT'], series: [{ nome: 'Senadores', valores: [14, 9] }] } },
      { tipo: 'rede', rede: { titulo: 'Conexões do PL', nos: [{ id: 'pl', rotulo: 'PL', grupo: 'Partido' }, { id: 's1', rotulo: 'Senador A', grupo: 'Senador' }], arestas: [{ origem: 's1', destino: 'pl', rotulo: 'filiado' }] } },
      { tipo: 'resposta', texto: 'O **PL** lidera. [Fato oficial]', modelo: 'm' },
    ].map((l) => JSON.stringify(l)).join('\n') + '\n'
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url === '/api/agente'
      ? new Response(lines, { headers: { 'content-type': 'application/x-ndjson' } })
      : new Response(JSON.stringify(DATA[url.split('?')[0]] ?? []), { status: 200 })))
    localStorage.clear()
    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Abrir agente político' }))
    await userEvent.type(screen.getByLabelText('Pergunta ao agente'), 'Qual a maior bancada?{Enter}')
    expect(await screen.findByText('lidera. [Fato oficial]', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Lendo /senado/composicao/2026-11-24')).toBeInTheDocument()
    expect(screen.getByLabelText('Bancadas por partido')).toBeInTheDocument()
    expect(screen.getByLabelText('Conexões do PL')).toBeInTheDocument()
    const body = JSON.parse((fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls.find(([u]) => u === '/api/agente')![1].body as string)
    expect(body.mensagens).toEqual([{ papel: 'usuario', texto: 'Qual a maior bancada?' }])
    await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar' })).toBeInTheDocument())
  })
})
