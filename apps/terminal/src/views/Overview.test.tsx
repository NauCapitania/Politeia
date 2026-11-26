import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Overview } from './Overview'
import { ontology } from '../test/ontology'
import { useStore } from '../store'

const renderMap = async (graph = true) => {
  const result = render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Overview /></QueryClientProvider>)
  if (graph) await userEvent.click(await screen.findByRole('tab', { name: 'Grafo' }))
  return result
}
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
    await renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Presidência da República' }))
    const detail = within(screen.getByRole('complementary'))
    expect(detail.queryByRole('button', { name: /Processar e julgar/ })).not.toBeInTheDocument()
    fireEvent.click(document.querySelector('[data-competence-id="cmp_julga"] .constellation-edge-hit')!)
    const selection = detail.getByRole('button', { name: /Processar e julgar/ })
    expect(selection).toHaveAttribute('aria-pressed', 'true')
    expect(within(selection.closest('article')!).getByText('Quórum: 54 senadores')).toBeInTheDocument()
    expect(within(selection.closest('article')!).getByRole('link', { name: /Constituição Federal/ })).toHaveAttribute('href', data.legal_bases[0].url)
  })
  it('prioriza os destinos selecionados numa camada com mais de dez vizinhos', async () => {
    const data = structuredClone(ontology)
    data.offices.push(...Array.from({ length: 11 }, (_, i) => ({ ...data.offices[0], id: `cargo_${i}`, name: `Cargo ${i}`, body_id: 'bod_presidencia' })))
    data.competences.push({ ...data.competences[0], id: 'indica_stf', verb: 'Indicar', holder_body_id: 'bod_presidencia' })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
    await renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Presidência da República' }))
    expect(screen.queryByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).not.toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('complementary')).getByRole('button', { name: /Indicar/ }))
    expect(screen.getByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).toBeInTheDocument()
    expect(document.querySelector('[data-competence-id="indica_stf"] .constellation-edge-hit')).toBeInTheDocument()
  })
  it.each([[false, false], [true, false], [false, true], [true, true]])('carrega a composição completa da comissão (Câmara: %s, cargo: %s)', async (camara, memberOffice) => {
    const data = structuredClone(ontology)
    data.bodies.push({ ...data.bodies[0], id: 'bod_com_teste', name: 'Comissão de teste', parent_id: camara ? 'bod_camara' : 'bod_senado', committee_id: 'com_teste' })
    data.offices.push({ ...data.offices[0], id: 'off_membro_comissao', name: 'Membro de comissão', body_id: null })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/comissoes/com_teste') ? { members: [{ person_id: 'per_novo', name: 'Integrante sem cargo de direção', role: null, seat_kind: 'suplente', party: 'PV', uf: 'SP', since: null }] } : data))))
    await renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    await userEvent.type(screen.getByRole('textbox', { name: 'Buscar órgão ou cargo' }), memberOffice ? 'Membro de comissão' : 'Comissão de teste')
    await userEvent.click(within(screen.getByLabelText('Resultados da busca')).getByRole('button'))
    if (memberOffice) {
      expect(screen.queryByText('Nenhum ocupante encontrado nesta camada. Isso não significa cargo vago.')).not.toBeInTheDocument()
      await userEvent.click(within(screen.getByRole('complementary')).getByRole('button', { name: /Comissão de teste/ }))
    }
    expect(await screen.findByText('Integrante sem cargo de direção')).toBeInTheDocument()
    expect(screen.queryByText('Nenhum ocupante encontrado nesta camada. Isso não significa cargo vago.')).not.toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url) === `/v1/${camara ? 'camara/' : ''}comissoes/com_teste`)).toBe(true)
  })
  it('não interpreta datas heterogêneas da origem como início no cargo', async () => {
    const data = structuredClone(ontology)
    data.holdings[0].origin = 'mandate'
    data.holdings[0].sources = [{ kind: 'official', outlet: 'Senado Federal', url: 'https://www25.senado.leg.br/web/senadores/' }]
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
    await renderMap()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Senado Federal' }))
    const detail = within(screen.getByRole('complementary'))
    await userEvent.click(detail.getByRole('button', { name: /Davi Alcolumbre/ }))
    expect(detail.getByRole('link', { name: /Senado Federal/ })).toBeInTheDocument()
    expect(detail.queryByText(/Início do mandato:|Em exercício desde/)).not.toBeInTheDocument()
  })
  it('separa três poderes das instituições autônomas e mostra os tribunais superiores', async () => {
    await renderMap()
    const group = await screen.findByRole('button', { name: 'Explorar Funções essenciais à Justiça' })
    expect(group).toHaveClass('autonomous')
    expect(group).not.toHaveClass('power')
    expect(document.querySelectorAll('.constellation-node.power')).toHaveLength(3)
    for (const name of ['Superior Tribunal de Justiça', 'Tribunal Superior Eleitoral', 'Tribunal Superior do Trabalho', 'Superior Tribunal Militar', 'Conselho Nacional de Justiça']) {
      expect(screen.getByRole('button', { name: `Explorar ${name}` })).toBeInTheDocument()
    }
    expect(screen.queryByText('Controle e Justiça')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Explorar Judiciário' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })
  it('explora poder, órgão, cargo e ocupante com a norma e sem notícias', async () => {
    await renderMap()
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
    await renderMap()
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
    await renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    await userEvent.click(screen.getByRole('button', { name: 'Caso Master' }))
    expect(screen.getByText(/não responsabilidade pessoal/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Explorar Presidência da República' })).toHaveClass('dimmed')
    await userEvent.click(screen.getByRole('button', { name: /Presidência do Senado 2027 ↗/ }))
    expect(useStore.getState()).toMatchObject({ view: 'senado', senadoTab: 'presidencia2027' })
  })
  it('funciona no snapshot estático sem chamar a API', async () => {
    vi.stubEnv('VITE_DATA_MODE', 'static')
    await renderMap()
    await screen.findByRole('button', { name: 'Explorar Senado Federal' })
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/data/ontologia.json')).toBe(true)
    expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url).startsWith('/data/'))).toBe(true)
    vi.unstubAllEnvs()
  })
  it('não inventa um mapa quando a consulta falha', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 503 })))
    await renderMap(false)
    expect(await screen.findByRole('alert')).toHaveTextContent('O mapa está indisponível')
    expect(screen.queryByRole('button', { name: 'Explorar Senado Federal' })).not.toBeInTheDocument()
  })
})
