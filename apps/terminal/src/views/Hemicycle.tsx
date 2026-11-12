import { useMemo } from 'react'
import { motion } from 'motion/react'
import type { Composition } from '../api/client'
import { partyColor } from '../format'
import { useStore } from '../store'

/** Seats laid out in concentric arcs; seat total comes from the institution, never hard-coded. */
export function hemicycleLayout(n: number, width: number) {
  const rows = Math.max(3, Math.round(Math.sqrt(n / 2.2)))
  const outer = width / 2 - 12
  const inner = outer * 0.38
  const radii = Array.from({ length: rows }, (_, i) => inner + ((outer - inner) * i) / Math.max(rows - 1, 1))
  const total = radii.reduce((s, r) => s + r, 0)
  const perRow = radii.map((r) => Math.max(1, Math.round((n * r) / total)))
  let diff = n - perRow.reduce((s, x) => s + x, 0)
  for (let i = rows - 1; diff !== 0; i = (i - 1 + rows) % rows) { perRow[i] += Math.sign(diff); diff -= Math.sign(diff) }
  const points: { x: number; y: number; angle: number }[] = []
  radii.forEach((r, ri) => {
    const k = perRow[ri]
    for (let j = 0; j < k; j++) {
      const angle = Math.PI - (k === 1 ? Math.PI / 2 : (Math.PI * j) / (k - 1))
      points.push({ x: width / 2 + r * Math.cos(angle), y: outer + 16 - r * Math.sin(angle), angle })
    }
  })
  points.sort((a, b) => b.angle - a.angle)
  const seatR = Math.min(((outer - inner) / rows) * 0.38, (Math.PI * inner) / perRow[0] / 2.4)
  return { points, seatR, height: outer + 32 }
}

export function Hemicycle({ comp, width = 640 }: { comp: Composition; width?: number }) {
  const { select, selectedId, hover, hoveredId, partyFilter } = useStore()
  const { points, seatR, height } = useMemo(() => hemicycleLayout(comp.seats.length, width), [comp.seats.length, width])
  const hoveredSeat = comp.seats.find((s) => s.person_id && s.person_id === hoveredId)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Composição do plenário">
      {comp.seats.map((s, i) => {
        const p = points[i]
        if (!p) return null
        const dim = partyFilter ? s.party_id !== partyFilter : false
        const sel = s.person_id === selectedId
        return (
          <motion.circle
            key={s.mandate_id ?? `empty-${i}`}
            className="seat"
            data-testid="seat"
            initial={{ opacity: 0, r: 0 }}
            animate={{ opacity: dim ? 0.16 : 1, r: sel ? seatR * 1.35 : seatR }}
            transition={{ duration: 0.35, delay: i * 0.004 }}
            cx={p.x} cy={p.y}
            fill={s.state === 'occupied' ? partyColor(s.party_abbreviation) : 'transparent'}
            stroke={sel ? '#fff' : s.state === 'occupied' ? 'none' : 'var(--line-strong)'}
            strokeDasharray={s.state === 'occupied' ? undefined : '2 2'}
            strokeWidth={sel ? 2 : 1}
            onMouseEnter={() => hover(s.person_id)}
            onMouseLeave={() => hover(null)}
            onClick={() => s.person_id && select(s.person_id)}
          >
            <title>{s.name ? `${s.name} · ${s.party_abbreviation ?? 's/ partido'} · ${s.represented_unit ?? ''}` : 'Assento sem membro observado'}</title>
          </motion.circle>
        )
      })}
      <text x={width / 2} y={height - 40} textAnchor="middle" fill="var(--fg-0)" fontSize={28} fontWeight={600}>
        {comp.observed_members}
      </text>
      <text x={width / 2} y={height - 20} textAnchor="middle" fill="var(--fg-2)" fontSize={11}>
        {hoveredSeat ? `${hoveredSeat.name} · ${hoveredSeat.party_abbreviation ?? ''}` : comp.seat_count ? `de ${comp.seat_count} assentos` : 'membros observados'}
      </text>
    </svg>
  )
}
