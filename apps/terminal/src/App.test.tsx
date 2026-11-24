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
  useStore.setState({ institutionId: null, view: 'senado', analysisId: null, agentDraft: null, senadoTab: 'composicao', sidebarCollapsed: false, selectedId: null, partyFilter: null, search: '' })
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

describe('Plataforma modular', () => {
  it('separa a instituição Supremo da análise Master e preserva a linha do tempo', async () => {
    mockFetch({ '/v1/dossies/stf-caso-master': { items: {
      minister: [{ id: 'min-1', name: 'Ministro de teste', seat: 1, sources: src }],
      procedure_actor: [], impeachment_step: [], timeline_event: [{ id: 'ev-1', date: '2026-11-24', track: 'caso', text: 'Evento de teste com fonte', status: 'fact_reported', sources: src }],
    } } })
    renderApp()
    await userEvent.click(screen.getByRole('button', { name: 'Supremo Tribunal Federal' }))
    expect(await screen.findByRole('heading', { name: 'Supremo Tribunal Federal' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Ministro de teste' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Linha do tempo' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Abrir análise do caso Master →' }))
    expect(await screen.findByRole('heading', { name: 'Caso Master' })).toBeInTheDocument()
    expect(screen.getByText('Evento de teste com fonte', { exact: false })).toBeInTheDocument()
    expect(useStore.getState()).toMatchObject({ view: 'analises', analysisId: 'caso-master' })
    await userEvent.click(screen.getByRole('button', { name: 'Todas as análises' }))
    expect(await screen.findByRole('heading', { name: 'Análises' })).toBeInTheDocument()
  })

  it('cria outra análise, conserva suas notas e prepara uma pergunta sem enviar automaticamente', async () => {
    useStore.setState({ view: 'analises' })
    const app = renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Nova análise' }))
    await userEvent.type(screen.getByLabelText('Título'), 'Orçamento e educação')
    await userEvent.type(screen.getByLabelText('Pergunta de análise'), 'Quais comissões examinam o orçamento?')
    await userEvent.click(screen.getByRole('button', { name: 'Criar caderno' }))
    await userEvent.type(screen.getByLabelText('Evidências, links e hipóteses'), 'Hipótese a verificar, sem conclusão.')
    app.unmount()
    renderApp()
    expect(await screen.findByLabelText('Evidências, links e hipóteses')).toHaveValue('Hipótese a verificar, sem conclusão.')
    await userEvent.click(screen.getByRole('button', { name: 'Investigar com o agente →' }))
    expect((await screen.findByLabelText('Pergunta ao agente') as HTMLTextAreaElement).value).toContain('Quais comissões examinam o orçamento?')
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/agente')).toBe(false)
  })

  it('mantém o mapa e os guias acessíveis mesmo sem uma instituição ingerida', async () => {
    mockFetch({ '/v1/institutions': [] })
    useStore.setState({ view: 'congresso' })
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Congresso Nacional' })).toBeInTheDocument()
    expect(screen.getByText('Como funciona o Congresso')).toBeInTheDocument()
  })

  it('envia apenas a pergunta revisada, sem título ou notas privados no contexto', async () => {
    localStorage.setItem('politeia.analises.v1', JSON.stringify([{ id: 'local-private', title: 'Título reservado', question: 'Pergunta reservada', notes: 'Notas privadas' }]))
    useStore.setState({ view: 'analises', analysisId: 'local-private' })
    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Investigar com o agente →' }))
    const input = await screen.findByLabelText('Pergunta ao agente')
    await userEvent.clear(input)
    await userEvent.type(input, 'Como funciona o Congresso?{Enter}')
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/agente')).toBe(true))
    const body = vi.mocked(fetch).mock.calls.find(([url]) => url === '/api/agente')![1]!.body as string
    expect(body).toContain('Como funciona o Congresso?')
    expect(body).not.toContain('Título reservado')
    expect(body).not.toContain('Pergunta reservada')
    expect(body).not.toContain('Notas privadas')
  })

  it('preserva cadernos alterados em outra aba ao salvar notas locais', async () => {
    const first = { id: 'local-one', title: 'Educação', question: 'Pergunta um', notes: '' }
    const other = { id: 'local-two', title: 'Saúde', question: 'Pergunta dois', notes: 'Evidência salva em outra aba' }
    localStorage.setItem('politeia.analises.v1', JSON.stringify([first]))
    useStore.setState({ view: 'analises', analysisId: first.id })
    renderApp()
    const input = await screen.findByLabelText('Evidências, links e hipóteses')
    // Another tab saves after this tab has loaded its local state.
    localStorage.setItem('politeia.analises.v1', JSON.stringify([first, other]))
    await userEvent.type(input, 'Nova nota')
    const saved = JSON.parse(localStorage.getItem('politeia.analises.v1')!)
    expect(saved).toContainEqual(other)
    expect(saved).toContainEqual({ ...first, notes: 'Nova nota' })
  })

  it('conserva a pergunta não enviada ao preparar uma investigação de caderno', async () => {
    localStorage.setItem('politeia.analises.v1', JSON.stringify([{ id: 'local-draft', title: 'Orçamento', question: 'Quais comissões?', notes: '' }]))
    useStore.setState({ view: 'analises', analysisId: 'local-draft' })
    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Abrir agente político' }))
    await userEvent.type(screen.getByLabelText('Pergunta ao agente'), 'Minha pergunta ainda não enviada')
    await userEvent.click(screen.getByRole('button', { name: 'Fechar agente' }))
    await userEvent.click(screen.getByRole('button', { name: 'Investigar com o agente →' }))
    const input = await screen.findByLabelText('Pergunta ao agente') as HTMLTextAreaElement
    expect(input.value).toContain('Minha pergunta ainda não enviada')
    expect(input.value).toContain('Quais comissões?')
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/agente')).toBe(false)
  })

  it('abre o catálogo ao voltar da central depois de visitar uma análise', async () => {
    useStore.setState({ view: 'inicio', analysisId: 'caso-master' })
    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Todas as análises' }))
    expect(await screen.findByRole('heading', { name: 'Análises' })).toBeInTheDocument()
    expect(useStore.getState().analysisId).toBeNull()
  })

  it('encontra o Supremo pela sigla STF sem renomear a instituição', async () => {
    renderApp()
    await userEvent.click(await screen.findByRole('button', { name: 'Buscar ou navegar' }))
    await userEvent.type(screen.getByRole('combobox', { name: 'Buscar espaços, senadores ou proposições' }), 'STF')
    expect(screen.getByRole('option', { name: /Supremo Tribunal Federal/ })).toBeInTheDocument()
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('heading', { name: 'Supremo Tribunal Federal' })).toBeInTheDocument()
  })

  it('não envia nem corta silenciosamente um rascunho acima do limite do agente', async () => {
    useStore.setState({ view: 'analises', agentDraft: 'a'.repeat(8001) })
    renderApp()
    const input = await screen.findByLabelText('Pergunta ao agente') as HTMLTextAreaElement
    expect(input.value).toHaveLength(8001)
    expect(screen.getByRole('alert')).toHaveTextContent('Reduza para até 8.000')
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
    await userEvent.click(input)
    await userEvent.keyboard('{Enter}')
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/agente')).toBe(false)
  })

  it('navega pelos poderes e explica etapas sem apresentar o roteiro como tramitação real', async () => {
    useStore.setState({ view: 'congresso' })
    renderApp()
    await screen.findByRole('heading', { name: 'Congresso Nacional' })
    await userEvent.click(screen.getByRole('button', { name: /Sanção ou veto/ }))
    expect(screen.getByText(/PECs seguem rito próprio/)).toBeInTheDocument()
    expect(screen.getByText(/não andamento de uma proposição específica/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Judiciário' }))
    expect(await screen.findByRole('heading', { name: 'Supremo Tribunal Federal' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Executivo' }))
    expect(useStore.getState().view).toBe('executivo')
    expect(await screen.findByText('Como funciona o Executivo')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Legislativo' }))
    await userEvent.click(await screen.findByRole('tab', { name: 'Senado Federal' }))
    expect(await screen.findByRole('tab', { name: 'Composição' })).toBeInTheDocument()
  })
})

describe('Snapshot estático', () => {
  it('mostra a data em BRT, carrega as cadeiras e filtra proposições sem a API', async () => {
    vi.stubEnv('VITE_DATA_MODE', 'static')
    const date = '2026-11-23'
    const snapshot: Record<string, unknown> = {
      '/data/meta.json': { generated_at: '2026-11-24T01:30:00Z', composition_dates: ['2023-02-01', date] },
      '/data/institutions.json': [inst],
      '/data/noticias.json': [],
      '/data/senado/mudancas.json': [],
      [`/data/senado/composicao/${date}.json`]: { date, observed: 1, seats: [{ ...seat(1), full_name: 'Nome Completo do Senador' }] },
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

      await user.click(screen.getByRole('button', { name: 'Politeia, início' }))
      expect(await screen.findByText('Base consultada · 23/11/2026')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Abrir terminal local' }))
      await user.type(screen.getByRole('textbox', { name: 'Comando do terminal' }), 'resumo{Enter}')
      expect(await screen.findByText(`Composição consultada: ${date}`)).toBeInTheDocument()
      expect(screen.getByText('1 cadeiras observadas; 1 partidos identificados.')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Fechar terminal' }))
      await user.click(screen.getByRole('button', { name: 'Buscar ou navegar' }))
      await user.type(screen.getByRole('combobox', { name: 'Buscar espaços, senadores ou proposições' }), 'Nome Completo do Senador')
      expect(screen.getByRole('option', { name: /Senador 1/ })).toBeInTheDocument()
      await user.keyboard('{Escape}')
      expect(fetchSnapshot.mock.calls.every(([url]) => url.startsWith('/data/'))).toBe(true)
      expect(fetchSnapshot.mock.calls.filter(([url]) => /\/composicao\//.test(url)).every(([url]) => url.endsWith(`${date}.json`) || url.endsWith('2023-02-01.json'))).toBe(true)
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
