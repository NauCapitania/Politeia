import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, scaleOrdinal, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { NetworkSpec } from './client'

const COLORS = ['#6ea8ff', '#4fb39a', '#d6a64a', '#d86a6a', '#b18cff', '#5cc8d6', '#e48bd0', '#9ccc65']
const W = 420
const H = 320

type Node = SimulationNodeDatum & { id: string; rotulo: string; grupo?: string; r: number }
type Link = SimulationLinkDatum<Node> & { rotulo?: string; peso: number }

export function Rede({ spec }: { spec: NetworkSpec }) {
  const svg = useRef<SVGSVGElement>(null)
  const [, setTick] = useState(0)
  const [foco, setFoco] = useState<string | null>(null)
  const color = useMemo(() => scaleOrdinal<string>().range(COLORS), [])
  const grupos = [...new Set(spec.nos.map((n) => n.grupo).filter(Boolean))] as string[]

  const { nodes, links, vizinhos } = useMemo(() => {
    const grau = new Map<string, number>()
    spec.arestas.forEach((a) => { grau.set(a.origem, (grau.get(a.origem) ?? 0) + 1); grau.set(a.destino, (grau.get(a.destino) ?? 0) + 1) })
    const nodes: Node[] = spec.nos.map((n, i) => {
      const angle = (i / spec.nos.length) * Math.PI * 2
      return { ...n, r: 3 + Math.sqrt((n.peso ?? 1) + (grau.get(n.id) ?? 0)) * 1.8, x: W / 2 + Math.cos(angle) * 60, y: H / 2 + Math.sin(angle) * 60 }
    })
    const links: Link[] = spec.arestas.map((a) => ({ source: a.origem, target: a.destino, rotulo: a.rotulo, peso: a.peso ?? 1 }))
    const vizinhos = new Map<string, Set<string>>()
    spec.arestas.forEach((a) => {
      vizinhos.set(a.origem, (vizinhos.get(a.origem) ?? new Set()).add(a.destino))
      vizinhos.set(a.destino, (vizinhos.get(a.destino) ?? new Set()).add(a.origem))
    })
    return { nodes, links, vizinhos }
  }, [spec])

  useEffect(() => {
    const sim = forceSimulation(nodes)
      .force('link', forceLink<Node, Link>(links).id((d) => d.id).distance(46).strength((l) => 0.25 + l.peso * 0.05))
      .force('charge', forceManyBody().strength(-70))
      .force('center', forceCenter(W / 2, H / 2))
      .force('x', forceX(W / 2).strength(0.04))
      .force('y', forceY(H / 2).strength(0.06))
      .force('collide', forceCollide<Node>((d) => d.r + 3))
      .on('tick', () => {
        nodes.forEach((n) => { n.x = Math.max(n.r, Math.min(W - n.r, n.x ?? 0)); n.y = Math.max(n.r, Math.min(H - n.r, n.y ?? 0)) })
        setTick((t) => t + 1)
      })
    const el = svg.current
    let drag: Node | null = null
    const point = (e: PointerEvent) => {
      const box = el!.getBoundingClientRect()
      return [((e.clientX - box.left) / box.width) * W, ((e.clientY - box.top) / box.height) * H]
    }
    const down = (e: PointerEvent) => {
      const id = (e.target as Element).closest('[data-no]')?.getAttribute('data-no')
      drag = nodes.find((n) => n.id === id) ?? null
      if (!drag) return
      el!.setPointerCapture(e.pointerId)
      sim.alphaTarget(0.3).restart()
    }
    const move = (e: PointerEvent) => {
      if (!drag) return
      ;[drag.fx, drag.fy] = point(e)
    }
    const up = () => {
      if (drag) { drag.fx = null; drag.fy = null }
      drag = null
      sim.alphaTarget(0)
    }
    el?.addEventListener('pointerdown', down)
    el?.addEventListener('pointermove', move)
    el?.addEventListener('pointerup', up)
    return () => {
      sim.stop()
      el?.removeEventListener('pointerdown', down)
      el?.removeEventListener('pointermove', move)
      el?.removeEventListener('pointerup', up)
    }
  }, [nodes, links])

  const ativo = (id: string) => !foco || foco === id || vizinhos.get(foco)?.has(id)
  const pos = (n: Node | string | number) => n as Node

  return (
    <figure className="agente-rede" aria-label={spec.titulo}>
      <figcaption>{spec.titulo}<span className="muted"> · {spec.nos.length} nós, {spec.arestas.length} conexões</span></figcaption>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img">
        <defs>
          <filter id="brilho" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <radialGradient id="fundo-rede"><stop offset="0%" stopColor="#14213a" /><stop offset="100%" stopColor="#07090d" /></radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#fundo-rede)" />
        <g className="arestas">
          {links.map((l, i) => {
            const s = pos(l.source)
            const t = pos(l.target)
            const on = !foco || s.id === foco || t.id === foco
            return (
              <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} className={on ? 'on' : 'off'} strokeWidth={0.5 + l.peso * 0.25}>
                {l.rotulo && <title>{`${s.rotulo} — ${t.rotulo}: ${l.rotulo}`}</title>}
              </line>
            )
          })}
        </g>
        <g className="nos">
          {nodes.map((n, i) => (
            <g key={n.id} data-no={n.id} transform={`translate(${n.x},${n.y})`} className={ativo(n.id) ? 'on' : 'off'}
              onPointerEnter={() => setFoco(n.id)} onPointerLeave={() => setFoco(null)}>
              <circle r={n.r} fill={color(n.grupo ?? '')} filter="url(#brilho)" style={{ animationDelay: `${(i % 12) * 0.25}s` }} />
              <text dy={-n.r - 3}>{n.rotulo}</text>
            </g>
          ))}
        </g>
      </svg>
      {grupos.length > 0 && (
        <div className="agente-legenda">
          {grupos.map((g) => <span key={g}><i style={{ background: color(g) }} />{g}</span>)}
        </div>
      )}
      {spec.nota && <p className="agente-nota">{spec.nota}</p>}
    </figure>
  )
}
