import { useId, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import type { Competence } from '../api/ontology'
import './constellation.css'

export type MapNode = { id: string; name: string; short: string; kind: string; power: string; x: number; y: number; detail: string }
type Edge = { id: string; a: string; b: string; competence?: Competence }
type Props = { nodes: MapNode[]; edges: Edge[]; focus: string; analysisIds: Set<string> | null; selectedCompetence: string | null; onExplore: (id: string) => void; onCompetence: (id: string) => void }
const COLORS: Record<string, string> = { pow_legislativo: 'var(--atlas-leg)', pow_executivo: 'var(--atlas-exec)', pow_judiciario: 'var(--atlas-jud)', grp_funcoes_justica: 'var(--atlas-ctrl)' }

export function OntologyMap({ nodes, edges, focus, analysisIds, selectedCompetence, onExplore, onCompetence }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  const [edgeHover, setEdgeHover] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const arrowId = useId()
  const scrollRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const viewport = scrollRef.current
    const canvas = viewport?.firstElementChild as HTMLElement | null
    if (viewport && canvas) viewport.scrollLeft = Math.max(0, (canvas.clientWidth - viewport.clientWidth) / 2)
  }, [focus])
  const height = focus === 'uniao' ? 1120 : 910
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const connections = edges.flatMap((e) => e.competence && byId.has(e.a) && byId.has(e.b) ? [e.competence] : [])
  const activeEdges = edges.filter((e) => e.competence && (e.a === hovered || e.b === hovered || e.id === edgeHover || e.id === selectedCompetence))
  const highlight = new Set([hovered, ...activeEdges.flatMap((e) => [e.a, e.b])])
  const showLabel = edges.find((e) => e.id === (edgeHover ?? selectedCompetence))?.competence
  const radius = (n: MapNode) => n.id === 'uniao' ? 56 : n.kind === 'Poder constitucional' || n.kind === 'Agrupamento de leitura' ? 46 : n.id === focus ? 52 : 30
  return <div className="constellation">
    <div className="constellation-tools" aria-label="Controles do mapa"><button aria-label="Aproximar mapa" disabled={zoom >= 1.6} onClick={() => setZoom(Math.min(1.6, zoom + .2))}>+</button><button aria-label="Afastar mapa" disabled={zoom <= .8} onClick={() => setZoom(Math.max(.8, zoom - .2))}>−</button><button onClick={() => setZoom(1)}>Ajustar</button></div>
    <div className="atlas-map-scroll" ref={scrollRef}><div className="constellation-canvas" style={{ width: `${zoom * 100}%`, aspectRatio: `1000/${height}` }}>
      <svg viewBox={`0 0 1000 ${height}`} className="constellation-lines" aria-hidden="true"><defs><radialGradient id={`${arrowId}-glow`}><stop offset="0%" stopColor="var(--accent)" stopOpacity=".09" /><stop offset="100%" stopColor="var(--accent)" stopOpacity="0" /></radialGradient><marker id={arrowId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" fill="context-stroke" /></marker></defs>
        <circle cx="500" cy="445" r="420" fill={`url(#${arrowId}-glow)`} />
        {[130, 255, 390].map((r) => <circle key={r} cx="500" cy="445" r={r} className="constellation-orbit" />)}
        <path d="M500 30V860M60 445H940" className="constellation-axis" />
        {focus === 'uniao' && <path d="M100 885H900" className="constellation-orbit" />}
        {edges.map((e, i) => {
          const a = byId.get(e.a); const b = byId.get(e.b); if (!a || !b) return null
          const dx = b.x - a.x; const dy = b.y - a.y; const distance = Math.hypot(dx, dy) || 1
          const bend = e.competence ? 45 + i % 4 * 28 : 0
          const cx = (a.x + b.x) / 2 - dy / distance * bend; const cy = (a.y + b.y) / 2 + dx / distance * bend
          const ad = Math.hypot(cx - a.x, cy - a.y) || 1; const bd = Math.hypot(cx - b.x, cy - b.y) || 1
          const start = { x: a.x + (cx - a.x) / ad * radius(a), y: a.y + (cy - a.y) / ad * radius(a) }
          const end = { x: b.x + (cx - b.x) / bd * (radius(b) + 5), y: b.y + (cy - b.y) / bd * (radius(b) + 5) }
          const d = `M${start.x},${start.y}Q${cx},${cy} ${end.x},${end.y}`
          const lit = activeEdges.includes(e)
          return <g key={`${e.competence ? 'c' : 's'}${e.id}`} data-competence-id={e.competence?.id} style={{ '--edge-color': COLORS[a.power] ?? 'var(--accent)' } as CSSProperties} className={`constellation-edge ${e.competence ? 'competence' : 'structure'} ${lit ? 'lit' : ''} ${hovered && !lit ? 'muted' : ''}`}>
            <path d={d} markerEnd={e.competence ? `url(#${arrowId})` : undefined} />
            {e.competence && <path d={d} className="constellation-edge-hit" onMouseEnter={() => setEdgeHover(e.id)} onMouseLeave={() => setEdgeHover(null)} onClick={() => onCompetence(e.id)} />}
          </g>
        })}
      </svg>
      {nodes.map((n) => {
        const power = n.kind === 'Poder constitucional'
        const group = n.kind === 'Instituições autônomas'
        const dimmed = (analysisIds && !analysisIds.has(n.id) && !power && !group && n.id !== 'uniao') || (hovered && activeEdges.length > 0 && !highlight.has(n.id))
        return <button key={n.id} aria-label={`Explorar ${n.name}`} title={`${n.name} · ${n.detail}`} aria-current={n.id === focus ? 'true' : undefined} className={`constellation-node ${power ? 'power' : ''} ${group ? 'autonomous' : ''} ${n.id === focus ? 'focused' : ''} ${n.id === 'uniao' ? 'union' : ''} ${dimmed ? 'dimmed' : ''}`} style={{ left: `${n.x / 10}%`, top: `${n.y / height * 100}%`, '--node-color': COLORS[n.power] ?? 'var(--accent)' } as CSSProperties} onMouseEnter={() => setHovered(n.id)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(n.id)} onBlur={() => setHovered(null)} onClick={() => { setHovered(null); onExplore(n.id) }}><span className="constellation-sphere"><span>{n.short}</span></span><strong>{n.name}</strong>{(power || n.id === 'uniao') && <small>{n.detail}</small>}</button>
      })}
    </div></div>
    <div className="constellation-readout" aria-live="polite">{showLabel ? <><span>COMPETÊNCIA LEGAL</span><b>{showLabel.verb}</b><p>{showLabel.target_label}</p></> : hovered && byId.has(hovered) ? <><span>{byId.get(hovered)!.kind}</span><b>{byId.get(hovered)!.name}</b><p>{byId.get(hovered)!.detail}</p></> : <><span>RELAÇÕES INSTITUCIONAIS</span><p>Passe por uma instituição para destacar seus vínculos.<br />Clique em uma linha para consultar a competência.</p></>}</div>
    {!!connections.length && <details className="constellation-connections"><summary>Competências no grafo ({connections.length})</summary><ul>{connections.map((c) => <li key={c.id}><button aria-pressed={selectedCompetence === c.id} onFocus={() => setEdgeHover(c.id)} onBlur={() => setEdgeHover(null)} onClick={() => onCompetence(c.id)}><strong>{c.verb}</strong><span>{c.target_label}</span></button></li>)}</ul></details>}
  </div>
}
