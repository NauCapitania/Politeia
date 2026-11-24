import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { Partidos } from '../Partidos'
import type { PartyDossier } from './data'

const sources = [{ url: 'https://www.tse.jus.br/partidos', outlet: 'TSE', kind: 'official' }]
const fixture: PartyDossier = {
  as_of: '2026-11-24',
  items: {
    party: [
      { id: 'party-dem', partyId: 'dem', name: 'Democratas', abbreviation: 'DEM', sources },
      { id: 'party-uniao', partyId: 'uniao', name: 'União Brasil', abbreviation: 'UNIÃO', sources },
    ],
    event: [
      { id: 'dem-reg', type: 'registro', date: '2007', from: [], to: ['dem'], title: 'Registro de DEM', summary: 'Registro', sources },
      { id: 'partidos-fusao-uniao', type: 'fusao', date: '2022-02-08', from: ['dem'], to: ['uniao'], title: 'Formação de União',
        summary: 'Fusão', people: ['Pessoa A'], declared: 'Objetivo declarado', analysis: 'Hipótese, não prova', sources },
    ],
    funding: [
      { id: 'fefc-2020', fund: 'fefc', year: 2020, totalCents: 10000, allocations: [{ partyId: 'dem', cents: 2000 }], note: 'Cotas', sources },
      { id: 'fefc-2026', fund: 'fefc', year: 2026, totalCents: 20000, allocations: [{ partyId: 'uniao', cents: 5000 }], note: 'Cotas', sources },
      { id: 'part-2026', fund: 'partidario', year: 2026, totalCents: 25000, allocations: [{ partyId: 'uniao', cents: 5000 }], note: 'Até outubro', partial: true, sources },
    ],
    comparison: [{ id: 'comparacao', fund: 'fefc', title: 'Antes e depois', before: { year: 2020, partyIds: ['dem'] },
      after: { year: 2026, partyIds: ['uniao'] }, text: 'Sem inferência causal', sources }],
    site: [{ id: 'site-uniao', partyId: 'uniao', title: 'União Brasil', text: 'Estatuto', sources }],
  },
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

function setup(data: PartyDossier | null = fixture) {
  vi.stubEnv('VITE_DATA_MODE', 'static')
  const fetch = vi.fn(async () => Response.json(data))
  vi.stubGlobal('fetch', fetch)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Partidos />
  </QueryClientProvider>)
  return fetch
}

it('lê o snapshot e diferencia o evento documentado, a declaração e a análise', async () => {
  const fetch = setup()
  const chronology = await screen.findByRole('region', { name: 'Cronologia e evidências' })
  expect(fetch).toHaveBeenCalledWith('/data/dossies/partidos.json')
  expect(within(chronology).getByText('Objetivo declarado')).toBeVisible()
  expect(within(chronology).getByText('Hipótese, não prova')).toBeVisible()
  const graph = screen.getByRole('region', { name: 'Gráfico de linhagem partidária' })
  await userEvent.click(within(graph).getByRole('button', { name: 'Registro de DEM' }))
  expect(within(chronology).getByRole('heading', { name: 'Registro de DEM' })).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Evento'), 'fusao')
  expect(within(graph).queryByRole('button', { name: 'Registro de DEM' })).not.toBeInTheDocument()
})

it('mostra cotas e participação por ano, compara a fusão e avisa que o Fundo Partidário é parcial', async () => {
  setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Financiamento' }))
  const distributions = screen.getByRole('region', { name: 'Distribuição por legenda' })
  expect(within(distributions).getByText('25%')).toBeVisible()
  expect(screen.getByText('20% do FEFC')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: /^2020:/ }))
  expect(within(distributions).getByText('20%')).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Fundo'), 'partidario')
  expect(screen.getByText(/Período parcial/)).toBeVisible()
  expect(within(distributions).getByText('Até outubro')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Sites partidários' }))
  expect(screen.getByRole('heading', { name: 'União Brasil' })).toBeVisible()
})

it('explica quando um snapshot ainda não contém o dossiê', async () => {
  setup(null)
  expect(await screen.findByText('Dossiê de partidos indisponível nesta versão dos dados.')).toBeVisible()
})
