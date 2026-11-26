import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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
