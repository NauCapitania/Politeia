import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { useStore } from './store'
import { hemicycleLayout } from './views/Hemicycle'

const inst = (id: string, short: string, seats: number | null) => ({
  id, slug: id, official_name: `${short} oficial`, short_name: short, institution_type: 'chamber', jurisdiction: 'J',
  geographic_scope: short === 'Senado' ? 'Brasil' : 'Pernambuco', country: 'BR', website: 'https://example.leg.br',
  seat_count: seats, seat_count_status: seats ? 'verified' : 'unverified', seat_count_source: null,
  terminology: { members: 'Membros', represented_unit: 'UF' }, observed_member_count: 2, pack_id: id, pack_version: '0.1.0',
  last_ingested_at: '2026-11-12T00:00:00Z', sources: [{ id: 's', name: 'Fonte', base_url: 'https://x', documentation_url: null }],
})
const party = { id: 'pty_a', abbreviation: 'PA', name: null }
const seat = (i: number, name: string) => ({ index: i, person_id: `per_${name}`, mandate_id: `man_${name}`, name, party_abbreviation: 'PA', party_id: 'pty_a', represented_unit: 'PE', participation: null, state: 'occupied' })
const DATA: Record<string, unknown> = {
  '/v1/institutions': [inst('ins_br_senado', 'Senado', 81), inst('ins_pe_alepe', 'ALEPE', null)],
  '/v1/institutions/ins_br_senado/composition': { institution_id: 'ins_br_senado', seat_count: 81, seat_count_status: 'verified', observed_members: 2, seats: [seat(0, 'Ana'), seat(1, 'Bia'), ...Array.from({ length: 79 }, (_, i) => ({ index: i + 2, person_id: null, mandate_id: null, name: null, party_abbreviation: null, party_id: null, represented_unit: null, participation: null, state: 'unobserved' }))], groups: [{ party, count: 2 }], discrepancy: '79 seats without an observed member' },
  '/v1/institutions/ins_pe_alepe/composition': { institution_id: 'ins_pe_alepe', seat_count: null, seat_count_status: 'unverified', observed_members: 2, seats: [seat(0, 'Caio'), seat(1, 'Duda')], groups: [{ party, count: 2 }], discrepancy: 'Official seat count not verified; composition shows observed members only' },
  '/v1/institutions/ins_br_senado/capabilities': [{ capability: 'members', status: 'available', record_count: 2, coverage: {}, last_success_at: null, note: null, issues: [] }],
  '/v1/institutions/ins_pe_alepe/capabilities': [{ capability: 'party_history', status: 'unavailable_in_source', record_count: null, coverage: {}, last_success_at: null, note: 'Source publishes no party history', issues: [] }],
  '/v1/entities/per_Ana': { id: 'per_Ana', kind: 'person', label: 'Ana', attributes: { profile_url: 'https://www25.senado.leg.br/ana' }, identifiers: [{ scheme: 'senado.parlamentar', value: '1', quality: 'official' }], sources: [{ raw_record_id: 'r1', url: 'https://legis.senado.leg.br/dadosabertos/senador/lista/atual', record_kind: 'member_list', json_path: '$.x', retrieved_at: '2026-11-12T00:00:00Z', content_sha256: 'a'.repeat(64) }] },
  '/v1/entities/per_Ana/relationships': [{ id: 'm1', kind: 'holds_mandate', source: 'per_Ana', target: 'man_Ana', label: 'Senador(a) titular', valid_from: '2023-02-01', valid_to: null, is_current: true, epistemic_status: 'verified', explanation: 'x', sources: [] }],
  '/v1/entities/per_Ana/timeline': [],
}

function mockFetch() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = DATA[path] ?? (path.endsWith('/members') || path.endsWith('/proposals') ? { items: [], total: 0, limit: 50, offset: 0 } : [])
    return new Response(JSON.stringify(body), { status: 200 })
  }))
}

const renderApp = () => render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>)

beforeEach(() => {
  useStore.setState({ institutionId: null, view: 'overview', selectedId: null, partyFilter: null, search: '' })
  mockFetch()
})

describe('Politeia terminal', () => {
  it('lays out exactly the institution seat count', () => {
    expect(hemicycleLayout(81, 640).points).toHaveLength(81)
    expect(hemicycleLayout(49, 640).points).toHaveLength(49)
  })

  it('renders composition from the API and switches institution through the same interface', async () => {
    renderApp()
    expect(await screen.findByText('Senado oficial', { selector: 'h1' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
    await userEvent.selectOptions(screen.getByLabelText('Instituição'), 'ins_pe_alepe')
    expect(await screen.findByText('ALEPE oficial', { selector: 'h1' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(2))
    expect(screen.getByText(/Official seat count not verified/)).toBeInTheDocument()
    expect(screen.getAllByText('Indisponível na fonte').length).toBeGreaterThan(0)
  })

  it('selecting a seat opens the inspector with identifiers and official source', async () => {
    renderApp()
    await waitFor(() => expect(screen.getAllByTestId('seat')).toHaveLength(81))
    await userEvent.click(screen.getAllByTestId('seat')[0])
    const inspector = screen.getByLabelText('Inspetor')
    expect(await within(inspector).findByText('senado.parlamentar')).toBeInTheDocument()
    expect(within(inspector).getByText('Página oficial ↗')).toHaveAttribute('href', 'https://www25.senado.leg.br/ana')
    expect(within(inspector).getByText(/legis\.senado\.leg\.br/)).toBeInTheDocument()
  })
})
