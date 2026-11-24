import { partyColor, fmtDate } from '../../format'
import { shortName, type Body } from './data'

const DAY = 86400000
const ROW = 18
const LABEL = 210

/** One row per pasta; each bar is a term, colored by party, hatched when interim. */
export function CabinetTimeline({ bodies, selected, onSelect, from = '2023-01-01' }: {
  bodies: Body[]; selected?: string | null; onSelect: (code: string) => void; from?: string
}) {
  const rows = bodies.filter((b) => b.terms.length)
  const t0 = Date.parse(`${from}T00:00:00`)
  const t1 = Date.now() + 30 * DAY
  const width = 980
  const x = (d: string | null | undefined) => LABEL + ((d ? Date.parse(`${d}T12:00:00`) : Date.now()) - t0) / (t1 - t0) * (width - LABEL - 8)
  const years: number[] = []
  for (let y = new Date(t0).getFullYear(); y <= new Date(t1).getFullYear(); y++) years.push(y)
  const height = rows.length * ROW + 24
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Linha do tempo dos ministros" className="exe-timeline">
      <defs>
        <pattern id="exe-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="5" height="5" fill="var(--bg-2)" /><line x1="0" y1="0" x2="0" y2="5" stroke="var(--fg-2)" strokeWidth="2" />
        </pattern>
      </defs>
      {years.map((y) => {
        const xx = x(`${y}-01-01`)
        return xx >= LABEL ? (
          <g key={y}>
            <line x1={xx} x2={xx} y1={14} y2={height} stroke="var(--line)" />
            <text x={xx + 3} y={10} fontSize={10} fill="var(--fg-3)">{y}</text>
          </g>
        ) : null
      })}
      {rows.map((b, i) => {
        const y = 18 + i * ROW
        return (
          <g key={b.code} onClick={() => onSelect(b.code)} style={{ cursor: 'pointer' }} data-testid="timeline-row">
            <rect x={0} y={y - 2} width={width} height={ROW} fill={selected === b.code ? 'var(--accent-soft)' : 'transparent'} />
            <text x={4} y={y + 10} fontSize={10.5} fill={selected === b.code ? 'var(--fg-0)' : 'var(--fg-1)'}>
              {shortName(b).length > 34 ? `${shortName(b).slice(0, 33)}…` : shortName(b)}
            </text>
            {b.terms.map((t) => {
              const x1 = Math.max(LABEL, x(t.start))
              const x2 = Math.max(x1 + 2, x(t.end))
              return (
                <rect key={t.id} x={x1} y={y} width={x2 - x1 - 1} height={ROW - 5} rx={2}
                  fill={t.interim ? 'url(#exe-hatch)' : partyColor(t.party)} opacity={t.current ? 1 : 0.75}>
                  <title>{`${t.name}${t.party ? ` (${t.party})` : ' (sem partido)'}${t.interim ? ' · interino(a)' : ''}\n${fmtDate(t.start)} – ${t.end ? fmtDate(t.end) : 'em exercício'}`}</title>
                </rect>
              )
            })}
          </g>
        )
      })}
      <line x1={x(null)} x2={x(null)} y1={14} y2={height} stroke="var(--accent)" strokeDasharray="3 2" />
    </svg>
  )
}
