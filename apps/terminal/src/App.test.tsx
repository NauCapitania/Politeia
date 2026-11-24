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

function mockFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(({ ...DATA, ...overrides })[url.split('?')[0]] ?? []), { status: 200 })))
}
const renderApp = () => render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>)

beforeEach(() => {
  localStorage.clear()
  useStore.setState({ institutionId: null, view: 'senado', senadoTab: 'composicao', sidebarCollapsed: false, selectedId: null, partyFilter: null, search: '' })
  mockFetch()
})

describe('Espaço de trabalho', () => {
  it('alterna entre temas e preserva a escolha ao reabrir o aplicativo', async () => {
    const first = renderApp()
    expect(localStorage.getItem('politeia-theme')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Alternar para modo claro' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(document.documentElement).not.toHaveClass('bp6-dark')
    expect(localStorage.getItem('politeia-theme')).toBe('light')
    first.unmount()
    renderApp()
    expect(screen.getByRole('button', { name: 'Alternar para modo escuro' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Alternar para modo escuro' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement).toHaveClass('bp6-dark')
  })

  it('executa consultas locais, mantém histórico e navega pelo terminal', async () => {
    useStore.setState({ view: 'inicio' })
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: 'Abrir terminal local' }))
    const input = screen.getByRole('textbox', { name: 'Comando do terminal' })
    await userEvent.type(input, 'abrir __proto__{Enter}')
    expect(await screen.findByText('Pasta não encontrada. Digite ajuda para ver os destinos disponíveis.')).toBeInTheDocument()
    expect(useStore.getState().view).toBe('inicio')
    await userEvent.type(input, 'resumo{Enter}')
    expect(await screen.findByText('81 cadeiras observadas; 2 partidos identificados.')).toBeInTheDocument()
    await userEvent.type(input, '{ArrowUp}')
    expect(input).toHaveValue('resumo')
    await userEvent.clear(input)
    await userEvent.type(input, 'limpar{Enter}')
    expect(screen.queryByText('81 cadeiras observadas; 2 partidos identificados.')).not.toBeInTheDocument()
    await userEvent.type(input, 'abrir notícias{Enter}')
    await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Comando do terminal' })).not.toBeInTheDocument())
    expect(useStore.getState().view).toBe('noticias')
    await userEvent.click(screen.getByRole('button', { name: 'Abrir terminal local' }))
    const reopened = screen.getByRole('textbox', { name: 'Comando do terminal' })
    await userEvent.type(reopened, '{ArrowUp}')
    expect(reopened).toHaveValue('abrir notícias')
  })

  it('recolhe pastas sem alterar o espaço de trabalho atual', async () => {
    renderApp()
    const folder = screen.getByRole('button', { name: 'Instituições' })
    expect(folder).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(folder)
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    expect(useStore.getState().view).toBe('senado')
    await userEvent.click(folder)
    expect(folder).toHaveAttribute('aria-expanded', 'true')
  })

  it('não transforma filiação desconhecida em um partido adicional', async () => {
    useStore.setState({ view: 'inicio' })
    mockFetch({ '/v1/senado/composicao': { date: '2026-11-24', observed: 3, seats: [seat(0), seat(1), { ...seat(2), party: null }] } })
    renderApp()
    await waitFor(() => expect(screen.getByRole('button', { name: /Distribuição de poder/ })).toHaveTextContent('2 partidos'))
    expect(screen.getByRole('img', { name: /Filiação não informada: 1 cadeiras/ })).toBeInTheDocument()
  })

  it('abre a central com dados da base e navega pelo mapa de poder', async () => {
    useStore.setState({ view: 'inicio' })
    renderApp()
    expect(await screen.findByRole('heading', { name: 'A política em perspectiva.' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Painel de evidências')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: /Distribuição de poder/ })).toHaveTextContent('2 partidos'))
    expect(screen.getByRole('img', { name: /PT: 41 cadeiras; PL: 40 cadeiras/ })).toBeInTheDocument()
    screen.getByRole('main').scrollTop = 124
    await userEvent.click(screen.getByRole('button', { name: /Explorar composição/ }))
    expect(screen.getByRole('main').scrollTop).toBe(0)
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
  })

  it('busca um senador e abre e fecha suas evidências', async () => {
    useStore.setState({ view: 'inicio' })
    mockFetch({ '/v1/senado/composicao': { date: '2026-11-24', observed: 1, seats: [{ ...seat(1), full_name: 'Senador Um' }] } })
    renderApp()
    await screen.findByRole('heading', { name: 'A política em perspectiva.' })
    await userEvent.keyboard('{Control>}k{/Control}')
    const input = await screen.findByRole('combobox')
    await userEvent.type(input, 'Senador Um')
    await userEvent.click(await screen.findByText('Senador 1', { exact: true }))
    expect(await screen.findByText('Senador Um')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByLabelText('Painel de evidências')).not.toBeInTheDocument())
  })

  it('navega por teclado e encaminha buscas à base de proposições', async () => {
    renderApp()
    await screen.findByRole('tab', { name: 'Composição' })
    await userEvent.click(screen.getByRole('button', { name: /Buscar ou navegar/ }))
    const input = await screen.findByRole('combobox')
    await userEvent.type(input, 'sucessao inexistente')
    await userEvent.keyboard('{ArrowDown}{ArrowUp}{Enter}')
    expect(useStore.getState()).toMatchObject({ view: 'senado', senadoTab: 'proposicoes', search: 'sucessao inexistente' })
    await waitFor(() => expect(screen.queryByRole('combobox', { name: 'Buscar espaços, senadores ou proposições' })).not.toBeInTheDocument())
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
