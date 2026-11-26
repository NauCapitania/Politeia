import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Overview } from './Overview'
import { ontology } from '../test/ontology'
import type { Ontology } from '../api/ontology'

beforeEach(() => vi.unstubAllEnvs())
function renderStructure(data: Ontology = ontology) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(data))))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Overview /></QueryClientProvider>)
}

describe('Estrutura e Grafo da União', () => {
  it('abre uma hierarquia União → três poderes → órgãos, sem cards de União e poderes', async () => {
    const data = structuredClone(ontology)
    data.bodies.push({ ...data.bodies[0], id: 'bod_tcu', name: 'Tribunal de Contas da União', parent_id: null })
    renderStructure(data)
    expect(await screen.findByRole('tab', { name: 'Estrutura' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('tab')).toHaveLength(2)
    const tree = within(screen.getByRole('tabpanel', { name: 'Estrutura' }))
    expect(tree.getByRole('heading', { name: 'União' })).toBeInTheDocument()
    expect(document.querySelectorAll('.structure-power')).toHaveLength(3)
    const leg = within(tree.getByRole('region', { name: 'Poder Legislativo' }))
    const senate = leg.getByRole('button', { name: 'Explorar Senado Federal' })
    expect(senate.closest('ul')?.parentElement).toHaveTextContent('Congresso Nacional')
    const tcu = leg.getByRole('button', { name: 'Explorar Tribunal de Contas da União' })
    expect(tcu.closest('li')?.parentElement).toHaveClass('structure-roots')
    const autonomous = within(tree.getByRole('region', { name: 'Funções essenciais à Justiça' }))
    expect(autonomous.getByText(/Não constituem um quarto poder/)).toBeInTheDocument()
    expect(autonomous.getByRole('button', { name: 'Explorar Defensoria Pública da União' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aproximar mapa' })).not.toBeInTheDocument()
    await userEvent.click(tree.getByRole('button', { name: 'Explorar Judiciário' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
    expect(tree.getByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).toBeInTheDocument()
  })

  it('abre detalhes apenas do órgão/cargo e preserva o foco ao alternar abas', async () => {
    renderStructure()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Supremo Tribunal Federal' }))
    expect(within(screen.getByRole('complementary')).getByRole('heading', { name: 'Supremo Tribunal Federal' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Explorar Ministro do STF' }))
    await userEvent.click(screen.getByRole('tab', { name: 'Grafo' }))
    expect(screen.getByRole('tabpanel', { name: 'Grafo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Explorar Ministro do STF' })).toHaveClass('focused')
    await userEvent.click(screen.getByRole('tab', { name: 'Estrutura' }))
    expect(screen.getByRole('button', { name: 'Explorar Ministro do STF' })).toHaveAttribute('aria-current', 'true')
    expect(within(screen.getByRole('complementary')).getByRole('heading', { name: 'Ministro do STF' })).toBeInTheDocument()
  })

  it('revela o caminho de uma busca mesmo fora dos primeiros órgãos visíveis', async () => {
    const data = structuredClone(ontology)
    data.bodies.push(...Array.from({ length: 8 }, (_, i) => ({ ...data.bodies[0], id: `extra_${i}`, name: `Órgão ${i}`, power_id: 'pow_executivo', parent_id: 'bod_presidencia', origin: 'imported' })),
      { ...data.bodies[0], id: 'justica', name: 'Z Ministério da Justiça', power_id: 'pow_executivo', parent_id: 'bod_presidencia', origin: 'imported' },
      { ...data.bodies[0], id: 'pf', name: 'Polícia Federal', power_id: 'pow_executivo', parent_id: 'justica' })
    renderStructure(data)
    await screen.findByRole('tab', { name: 'Estrutura' })
    expect(screen.queryByRole('button', { name: 'Explorar Polícia Federal' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'Buscar órgão ou cargo' }), 'Polícia Federal')
    await userEvent.click(within(screen.getByLabelText('Resultados da busca')).getByRole('button'))
    const tree = within(screen.getByRole('tabpanel', { name: 'Estrutura' }))
    expect(tree.getByRole('button', { name: 'Explorar Polícia Federal' })).toHaveAttribute('aria-current', 'true')
    expect(tree.getByRole('button', { name: 'Recolher órgãos de Z Ministério da Justiça' })).toHaveAttribute('aria-expanded', 'true')
    expect(tree.queryByRole('button', { name: 'Mostrar outros 0 órgãos' })).not.toBeInTheDocument()
  })

  it('expande e recolhe órgãos sem misturar competências com subordinação', async () => {
    const data = structuredClone(ontology)
    data.bodies.push({ ...data.bodies[0], id: 'comissao', name: 'Comissão do Senado', parent_id: 'bod_senado' })
    renderStructure(data)
    const tree = within(await screen.findByRole('tabpanel', { name: 'Estrutura' }))
    expect(tree.queryByRole('button', { name: 'Explorar Comissão do Senado' })).not.toBeInTheDocument()
    await userEvent.click(tree.getByRole('button', { name: 'Expandir órgãos de Senado Federal' }))
    await userEvent.click(tree.getByRole('button', { name: 'Explorar Comissão do Senado' }))
    await userEvent.click(tree.getByRole('button', { name: 'Recolher órgãos de Senado Federal' }))
    expect(tree.queryByRole('button', { name: 'Explorar Comissão do Senado' })).not.toBeInTheDocument()
    expect(tree.getByRole('button', { name: 'Explorar Senado Federal' })).toHaveAttribute('aria-current', 'true')
    expect(within(tree.getByRole('region', { name: 'Poder Legislativo' })).queryByRole('button', { name: 'Explorar Supremo Tribunal Federal' })).not.toBeInTheDocument()
  })

  it('abre a competência no Grafo e mantém a norma disponível', async () => {
    renderStructure()
    await userEvent.click(await screen.findByRole('button', { name: 'Explorar Senado Federal' }))
    await userEvent.click(within(screen.getByRole('complementary')).getByRole('button', { name: /Processar e julgar/ }))
    expect(screen.getByRole('tab', { name: 'Grafo' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'Competências' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(screen.getByRole('complementary')).getByText('Quórum: 54 senadores')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'União' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })

  it('permite trocar as duas abas por teclado', async () => {
    renderStructure()
    await userEvent.click(await screen.findByRole('tab', { name: 'Estrutura' }))
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Grafo' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Grafo' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.keyboard('{Home}')
    expect(screen.getByRole('tab', { name: 'Estrutura' })).toHaveFocus()
    await userEvent.keyboard('{End}{ArrowLeft}')
    expect(screen.getByRole('tab', { name: 'Estrutura' })).toHaveAttribute('aria-selected', 'true')
  })
})
