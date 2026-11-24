import { arc, line, pie, scaleBand, scaleLinear, scaleOrdinal } from 'd3'
import type { ChartSpec } from './client'

const COLORS = ['#6ea8ff', '#4fb39a', '#d6a64a', '#d86a6a', '#b18cff', '#5cc8d6']
const W = 400
const H = 220
const M = { t: 10, r: 10, b: 46, l: 38 }
const fmt = (v: number) => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(v)

export function Grafico({ spec }: { spec: ChartSpec }) {
  const color = scaleOrdinal<string>().range(COLORS)
  return (
    <figure className="agente-grafico" aria-label={spec.titulo}>
      <figcaption>{spec.titulo}{spec.unidade ? <span className="muted"> ({spec.unidade})</span> : null}</figcaption>
      {spec.tipo === 'pizza' ? <Pizza spec={spec} color={color} /> : <Cartesiano spec={spec} color={color} />}
      {(spec.series.length > 1 || spec.tipo === 'pizza') && (
        <div className="agente-legenda">
          {(spec.tipo === 'pizza' ? spec.rotulos : spec.series.map((s) => s.nome)).map((nome) => (
            <span key={nome}><i style={{ background: color(nome) }} />{nome}</span>
          ))}
        </div>
      )}
      {spec.nota && <p className="agente-nota">{spec.nota}</p>}
    </figure>
  )
}

function Cartesiano({ spec, color }: { spec: ChartSpec; color: (k: string) => string }) {
  const max = Math.max(0, ...spec.series.flatMap((s) => s.valores))
  const min = Math.min(0, ...spec.series.flatMap((s) => s.valores))
  const x = scaleBand().domain(spec.rotulos).range([M.l, W - M.r]).padding(0.2)
  const y = scaleLinear().domain([min, max || 1]).nice().range([H - M.b, M.t])
  const inner = scaleBand().domain(spec.series.map((s) => s.nome)).range([0, x.bandwidth()]).padding(0.08)
  const tilt = spec.rotulos.length > 6
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img">
      {y.ticks(4).map((t) => (
        <g key={t} transform={`translate(0,${y(t)})`}>
          <line x1={M.l} x2={W - M.r} className="grid" />
          <text x={M.l - 4} dy="0.32em" textAnchor="end">{fmt(t)}</text>
        </g>
      ))}
      {spec.tipo === 'barra'
        ? spec.series.map((s) => s.valores.map((v, i) => (
          <rect key={`${s.nome}${i}`} x={x(spec.rotulos[i])! + inner(s.nome)!} width={inner.bandwidth()}
            y={y(Math.max(0, v))} height={Math.abs(y(v) - y(0))} fill={color(s.nome)} rx={1.5}>
            <title>{`${spec.rotulos[i]} · ${s.nome}: ${fmt(v)}`}</title>
          </rect>
        )))
        : spec.series.map((s) => (
          <g key={s.nome}>
            <path d={line<number>((_, i) => x(spec.rotulos[i])! + x.bandwidth() / 2, (v) => y(v))(s.valores) ?? ''}
              fill="none" stroke={color(s.nome)} strokeWidth={2} />
            {s.valores.map((v, i) => (
              <circle key={i} cx={x(spec.rotulos[i])! + x.bandwidth() / 2} cy={y(v)} r={2.5} fill={color(s.nome)}>
                <title>{`${spec.rotulos[i]} · ${s.nome}: ${fmt(v)}`}</title>
              </circle>
            ))}
          </g>
        ))}
      {spec.rotulos.map((r) => (
        <text key={r} className="rotulo" transform={`translate(${x(r)! + x.bandwidth() / 2},${H - M.b + 12})${tilt ? ' rotate(-35)' : ''}`}
          textAnchor={tilt ? 'end' : 'middle'}>{r.length > 14 ? `${r.slice(0, 13)}…` : r}</text>
      ))}
    </svg>
  )
}

function Pizza({ spec, color }: { spec: ChartSpec; color: (k: string) => string }) {
  const values = spec.series[0].valores
  const total = values.reduce((a, b) => a + b, 0) || 1
  const slices = pie<number>().sort(null)(values.map((v) => Math.max(0, v)))
  const shape = arc<{ startAngle: number; endAngle: number }>().innerRadius(48).outerRadius(90)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img">
      <g transform={`translate(${W / 2},${H / 2})`}>
        {slices.map((s, i) => (
          <path key={spec.rotulos[i]} d={shape(s) ?? ''} fill={color(spec.rotulos[i])} stroke="#0a0c10">
            <title>{`${spec.rotulos[i]}: ${fmt(values[i])} (${fmt((values[i] / total) * 100)}%)`}</title>
          </path>
        ))}
      </g>
    </svg>
  )
}
