import { useMemo } from 'react'
import { motion } from 'motion/react'
import * as d3 from 'd3'
import { Button } from '@blueprintjs/core'
import type { Institution, Graph } from '../api/client'
import { useGraph } from '../api/client'
import { useStore } from '../store'
import { EPISTEMIC_LABEL, partyColor } from '../format'

const KIND_COLOR: Record<string, string> = { institution: '#e6ebf2', person: '#6ea8ff', proposal: '#c9a227', mandate: '#7d8899' }
const EDGE_LABEL: Record<string, string> = {
  holds_mandate: 'exerce mandato', current_party: 'partido atual', party_affiliation: 'filiação', authored: 'autoria',
  represented_in: 'representado em', submitted_to: 'apresentada a',
}
const W = 860, H = 560

/** Focus-centred radial layout: rings by relationship type, so position carries meaning. */
function layout(g: Graph) {
  const pos = new Map<string, { x: number; y: number }>()
  pos.set(g.focus, { x: W / 2, y: H / 2 })
  const others = g.nodes.filter((n) => n.id !== g.focus)
  const groups = d3.group(others, (n) => n.kind)
  const kinds = [...groups.keys()]
  let start = -Math.PI / 2
  const total = others.length || 1
  kinds.forEach((k) => {
    const nodes = groups.get(k)!
    const span = (2 * Math.PI * nodes.length) / total
    nodes.forEach((n, i) => {
      const a = start + (span * (i + 0.5)) / nodes.length
      const r = k === 'proposal' ? 230 : k === 'institution' ? 120 : 170
      pos.set(n.id, { x: W / 2 + r * Math.cos(a), y: H / 2 + r * Math.sin(a) })
    })
    start += span
  })
  return pos
}

export function GraphView({ inst }: { inst: Institution }) {
  const { selectedId, select } = useStore()
  const graph = useGraph(inst.id, selectedId)
  const g = graph.data
  const pos = useMemo(() => (g ? layout(g) : new Map()), [g])
  return (
    <div className="view">
      <div className="view-header">
        <h1>Grafo institucional</h1>
        <span className="sub">{selectedId ? 'Relações do objeto selecionado' : `Partidos representados em ${inst.short_name}`}</span>
        <span style={{ flex: 1 }} />
        {selectedId && <Button size="small" icon="home" onClick={() => select(null)}>Instituição</Button>}
      </div>
      {g?.truncated && <div className="notice">Relações truncadas para legibilidade.</div>}
      <section className="panel">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Grafo de relações">
          {g?.edges.map((e) => {
            const a = pos.get(e.source), b = pos.get(e.target)
            if (!a || !b) return null
            return (
              <g key={e.id}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.is_current === false ? 'var(--line)' : 'var(--line-strong)'}
                  strokeDasharray={e.epistemic_status === 'verified' ? undefined : '4 3'}>
                  <title>{`${EDGE_LABEL[e.kind] ?? e.kind}: ${e.explanation} (${EPISTEMIC_LABEL[e.epistemic_status] ?? e.epistemic_status})`}</title>
                </line>
              </g>
            )
          })}
          {g?.nodes.map((n) => {
            const p = pos.get(n.id)
            if (!p) return null
            const focus = n.id === g.focus
            const color = n.kind === 'party' ? partyColor(n.label) : KIND_COLOR[n.kind] ?? '#888'
            const r = focus ? 14 : n.kind === 'party' ? 6 + Math.sqrt(Number(n.attributes?.members ?? 1)) * 2.4 : 6
            return (
              <motion.g key={n.id} initial={{ opacity: 0 }} animate={{ opacity: 1, x: p.x, y: p.y }} transition={{ duration: 0.4 }}
                style={{ cursor: 'pointer' }} onClick={() => select(n.id === inst.id ? null : n.id)} data-testid="graph-node">
                <circle r={r} fill={n.kind === 'institution' ? 'var(--bg-0)' : color} stroke={n.kind === 'institution' ? color : focus ? '#fff' : 'none'} strokeWidth={focus ? 2 : 1.5} />
                <text y={r + 13} textAnchor="middle" fontSize={n.kind === 'proposal' ? 9.5 : 11} fill="var(--fg-1)">{n.label}</text>
                <title>{n.kind}: {n.label}</title>
              </motion.g>
            )
          })}
        </svg>
        <div className="faint" style={{ padding: '8px 14px', fontSize: 11, borderTop: '1px solid var(--line)' }}>
          Linha contínua: relação verificada pela fonte · tracejada: extraída ou derivada · passe o mouse sobre uma aresta para a explicação.
        </div>
      </section>
    </div>
  )
}
