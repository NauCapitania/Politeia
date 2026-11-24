import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Executivo } from '../Executivo'
import { partyCounts, type Body } from './data'

const term = (id: string, name: string, party: string | null, start: string, end: string | null = null, interim = false) => ({
  id, person_id: `per_${id}`, name, party, uf: 'SP', interim, start, end, current: !end, epistemic_status: 'extracted',
  refs: [{ url: `https://g1.globo.com/${id}`, outlet: 'G1', date: start }],
})
const body = (code: string, name: string, kind: Body['kind'], terms: any[], extra: Partial<Body> = {}): Body => ({
  code, name, acronym: code, kind, administrative_units: 3, entities: [], terms,
  holder: terms.filter((t) => t.current).at(-1) ?? null, competence: `Competências de ${name}`, ...extra,
})
const DATA = {
  institution_id: 'ins_br_executivo',
  presidency: { code: '26', name: 'Presidência da República', competence: 'Sancionar, promulgar e fazer publicar as leis.' },
  counts: { bodies: 6, top_level: 3, ministries: 2, entities: 1, ministers_in_office: 3, terms: 4 },
  bodies: [
    body('SRI', 'Secretaria de Relações Institucionais da Presidência da República', 'presidencia', [term('a', 'José Guimarães', 'PT', '2026-04-14')]),
    body('MF', 'Ministério da Fazenda', 'ministerio', [term('b', 'Fernando Haddad', 'PT', '2023-01-01', '2026-03-19'), term('c', 'Dario Durigan', null, '2026-03-19')],
      { entities: [{ code: '900', name: 'Receita Exemplar', acronym: 'RE', legal_nature: 'Autarquia', direct: true }] }),
    body('MD', 'Ministério da Defesa', 'ministerio', [term('d', 'José Múcio', null, '2023-01-01')]),
  ],
  unmatched: [{ ministry: 'Secretaria Extraordinária do RS', title: 'x', terms: [term('e', 'Paulo Pimenta', 'PT', '2024-05-15', '2024-09-10')] }],
  sources: [{ id: 'src_br_siorg', name: 'SIORG', url: 'https://dados.gov.br/x', last_success_at: '2026-11-24T12:00:00Z' }],
}
const src = [{ url: 'https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm#art84', outlet: 'Constituição Federal', kind: 'official' }]
const GUIDE = {
  dossier: 'poder-executivo', items: {
    overview: [{ id: 'o', text: 'O Poder Executivo da União é exercido pelo Presidente da República.', sources: src }],
    office: [{ id: 'p', role: 'Presidente da República', name: 'Luiz Inácio Lula da Silva', party: 'PT', since: '2023-01-01', rule: 'Mandato de quatro anos.', sources: src }],
    power: [{ id: 'mp', group: 'Relação com o Congresso', article: 'Art. 62', title: 'Medidas provisórias', text: 'Força de lei.', links: ['congresso'], sources: src }],
    check: [{ id: 'imp', by: 'Câmara e Senado', article: 'Arts. 85 e 86', title: 'Crime de responsabilidade', text: 'Dois terços.', sources: src }],
  },
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const data = path === '/v1/executivo' ? DATA : path === '/v1/dossies/poder-executivo' ? GUIDE : null
    return new Response(JSON.stringify(data), { status: data ? 200 : 404 })
  }))
})
const renderView = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Executivo /></QueryClientProvider>)

describe('Poder Executivo', () => {
  it('conta partidos dos titulares em exercício', () => {
    expect(partyCounts(DATA.bodies)).toEqual([{ party: null, n: 2 }, { party: 'PT', n: 1 }])
  })

  it('mostra estrutura, titulares, histórico e entidades da pasta selecionada', async () => {
    renderView()
    expect(await screen.findByRole('heading', { name: 'Poder Executivo' })).toBeInTheDocument()
    expect(screen.getByText('O Poder Executivo da União é exercido pelo Presidente da República.')).toBeInTheDocument()
    expect(screen.getByText('Luiz Inácio Lula da Silva')).toBeInTheDocument()
    expect(screen.getAllByTestId('exe-body')).toHaveLength(3)
    await userEvent.click(screen.getByRole('button', { name: /Fazenda/ }))
    const detail = screen.getByTestId('exe-detail')
    expect(within(detail).getByRole('heading', { name: 'Ministério da Fazenda' })).toBeInTheDocument()
    expect(within(detail).getByText(/Fernando Haddad/)).toBeInTheDocument()
    expect(within(detail).getByText('Competências de Ministério da Fazenda')).toBeInTheDocument()
    expect(within(detail).getByText(/Receita Exemplar/)).toBeInTheDocument()
    await userEvent.type(screen.getByPlaceholderText(/Filtrar/), 'Múcio')
    expect(screen.getAllByTestId('exe-body')).toHaveLength(1)
  })

  it('desenha a linha do tempo e explica poderes e controles', async () => {
    renderView()
    await userEvent.click(await screen.findByRole('tab', { name: 'Linha do tempo do gabinete' }))
    expect(screen.getAllByTestId('timeline-row')).toHaveLength(3)
    expect(screen.getByText(/Secretaria Extraordinária do RS/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Como funciona' }))
    expect(screen.getByText('Medidas provisórias')).toBeInTheDocument()
    expect(screen.getByText('Crime de responsabilidade')).toBeInTheDocument()
    expect(screen.getByText('Sancionar, promulgar e fazer publicar as leis.')).toBeInTheDocument()
  })

  it('avisa quando os dados não existem no snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('null', { status: 404 })))
    renderView()
    expect(await screen.findByText('Dados do Poder Executivo ainda não carregados.')).toBeInTheDocument()
  })
})
