import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Overview } from './Overview'
import { ontology } from '../test/ontology'
import { useStore } from '../store'

const renderMap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Overview /></QueryClientProvider>)
beforeEach(() => {
  vi.unstubAllEnvs()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.includes('/ligacoes/') ? { note: 'Votações abertas', links: [{ a: 'per_1', b: 'per_2', weight: 0.8, shared: 25 }] } : ontology), { headers: { 'Content-Type': 'application/json' } })))
})
describe('Mapa da União', () => {
  it('mantém a norma de uma conexão selecionada entre vizinhos no inspetor', async () => {
    const data = structuredClone(ontology)
    data.competences.push(
      { ...data.competences[0], id: 'indica_stf', verb: 'Indicar', holder_body_id: 'bod_presidencia' },
      { ...data.competences[0], id: 'relacao_senado', verb: 'Relacionar', holder_body_id: 'bod_presidencia', target_office_id: 'off_pres_senado' },
    )
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
    renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Presidência da República' }))
    const detail = within(screen.getByRole('complementary'))
    expect(detail.queryByRole('button', { name: /Processar e julgar/ })).not.toBeInTheDocument()
    fireEvent.click(document.querySelector('[data-competence-id="cmp_julga"] .constellation-edge-hit')!)
    expect(detail.getByRole('button', { name: /Processar e julgar/ })).toHaveAttribute('aria-pressed', 'true')
    expect(detail.getByText('Quórum: 54 senadores')).toBeInTheDocument()
    expect(detail.getAllByRole('link', { name: /Constituição Federal/ }).some((a) => a.getAttribute('href') === data.legal_bases[0].url)).toBe(true)
  })
  it('prioriza os destinos selecionados numa camada com mais de dez vizinhos', async () => {
    const data = structuredClone(ontology)
    data.offices.push(...Array.from({ length: 11 }, (_, i) => ({ ...data.offices[0], id: `cargo_${i}`, name: `Cargo ${i}`, body_id: 'bod_presidencia' })))
    data.competences.push({ ...data.competences[0], id: 'indica_stf', verb: 'Indicar', holder_body_id: 'bod_presidencia' })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
    renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Presidência da República' }))
    expect(screen.queryByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).not.toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('complementary')).getByRole('button', { name: /Indicar/ }))
    expect(screen.getByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).toBeInTheDocument()
    expect(document.querySelector('[data-competence-id="indica_stf"] .constellation-edge-hit')).toBeInTheDocument()
  })
  it('distingue a data do mandato do início do exercício atual', async () => {
    const data = structuredClone(ontology)
    data.holdings[0].origin = 'mandate'
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
    renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Senado Federal' }))
    const detail = within(screen.getByRole('complementary'))
    await userEvent.click(detail.getByRole('button', { name: /Davi Alcolumbre/ }))
    expect(detail.getByText(/Início do mandato:/)).toBeInTheDocument()
    expect(detail.queryByText(/Em exercício desde/)).not.toBeInTheDocument()
  })
  it('separa três poderes das instituições autônomas e mostra os tribunais superiores', async () => {
    renderMap()
    const group = await screen.findByRole('button', { name: 'Explorar Funções essenciais à Justiça' })
    expect(group).toHaveClass('autonomous')
    expect(group).not.toHaveClass('power')
    expect(document.querySelectorAll('.constellation-node.power')).toHaveLength(3)
    for (const name of ['Superior Tribunal de Justiça', 'Tribunal Superior Eleitoral', 'Tribunal Superior do Trabalho', 'Superior Tribunal Militar', 'Conselho Nacional de Justiça']) {
      expect(screen.getByRole('button', { name: `Explorar ${name}` })).toBeInTheDocument()
    }
    expect(screen.queryByText('Controle e Justiça')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Explorar Judiciário' }))
    expect(within(screen.getByRole('complementary')).getByText('Órgãos nesta camada')).toBeInTheDocument()
  })
  it('explora poder, órgão, cargo e ocupante com a norma e sem notícias', async () => {
    renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Judiciário' }))
    await userEvent.click(screen.getByRole('button', { name: 'Explorar Supremo Tribunal Federal' }))
    await userEvent.click(screen.getByRole('button', { name: 'Explorar Ministro do STF' }))
    const detail = within(screen.getByRole('complementary', { name: 'Detalhes da ontologia' }))
    expect(detail.getByRole('heading', { name: 'Como se chega ao cargo' })).toBeInTheDocument()
    await userEvent.click(detail.getByRole('button', { name: /Cármen Lúcia/ }))
    expect(detail.getByText(/Indicação: Lula/)).toBeInTheDocument()
    expect(detail.getByRole('link', { name: /STF/ })).toHaveAttribute('href', 'https://portal.stf.jus.br')
    expect(screen.queryByText('Notícia aleatória')).not.toBeInTheDocument()
    expect(detail.getAllByRole('link', { name: /Constituição Federal/ })[0]).toHaveAttribute('href', ontology.legal_bases[0].url)
    await userEvent.click(screen.getByRole('button', { name: 'União' }))
    expect(screen.getByRole('button', { name: 'Explorar Executivo' })).toBeInTheDocument()
  })
  it('busca órgãos, explica competências e consulta apenas ligações observadas', async () => {
    renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    await userEvent.type(screen.getByRole('textbox', { name: 'Buscar órgão ou cargo' }), 'Senado Federal')
    await userEvent.click(within(screen.getByLabelText('Resultados da busca')).getByRole('button'))
    const detail = within(screen.getByRole('complementary', { name: 'Detalhes da ontologia' }))
    await userEvent.click(detail.getByRole('button', { name: /Processar e julgar/ }))
    expect(screen.getByRole('button', { name: 'Competências' })).toHaveAttribute('aria-pressed', 'true')
    expect(detail.getByText('Quórum: 54 senadores')).toBeInTheDocument()
    await userEvent.click(detail.getByRole('button', { name: /Votos em comum/ }))
    expect(await detail.findByText('80%')).toBeInTheDocument()
    expect(detail.getByText(/votos secretos não entram/)).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/ontologia/ligacoes/ins_br_senado'))).toBe(true)
  })
  it('mantém as análises e muda os destaques sem tratar menções como culpa', async () => {
    renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    await userEvent.click(screen.getByRole('button', { name: 'Caso Master' }))
    expect(screen.getByText(/não responsabilidade pessoal/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Explorar Presidência da República' })).toHaveClass('dimmed')
    await userEvent.click(screen.getByRole('button', { name: /Presidência do Senado 2027 ↗/ }))
    expect(useStore.getState()).toMatchObject({ view: 'senado', senadoTab: 'presidencia2027' })
  })
  it('funciona no snapshot estático sem chamar a API', async () => {
    vi.stubEnv('VITE_DATA_MODE', 'static')
    renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/data/ontologia.json')).toBe(true)
    expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url).startsWith('/data/'))).toBe(true)
    vi.unstubAllEnvs()
  })
  it('não inventa um mapa quando a consulta falha', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 503 })))
    renderMap()
    expect(await screen.findByRole('alert')).toHaveTextContent('O mapa está indisponível')
    expect(screen.queryByRole('button', { name: 'Explorar Senado Federal' })).not.toBeInTheDocument()
  })
})
