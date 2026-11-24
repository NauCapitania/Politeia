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
    await userEvent.click(await screen.findByRole('button', { name: /Presidência 2025/ }))
    expect(await screen.findByText(/O voto foi secreto/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
    await userEvent.click(screen.getAllByTestId('seat')[0])
    expect(await screen.findByText(/Justificativa/)).toBeInTheDocument()
    expect(screen.getAllByText('Hipótese').length).toBeGreaterThan(0)
  })
})
