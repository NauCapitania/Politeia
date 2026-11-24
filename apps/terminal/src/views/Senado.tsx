import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { Slider, Spinner, Tag } from '@blueprintjs/core'
import { useChanges, useSeats, type SeatRow } from '../api/client'
import { hemicycleLayout } from './Hemicycle'
import { partyColor, fmtDate } from '../format'
import { useStore } from '../store'

const START = Date.UTC(2023, 1, 1)
const DAY = 86400000
const iso = (t: number) => new Date(t).toISOString().slice(0, 10)
const KIND: Record<string, string> = { exercicio_inicio: 'Assume', exercicio_fim: 'Sai', troca_partido: 'Troca de partido' }

export function Senado() {
  const today = Math.floor(Date.now() / DAY) * DAY
  const [day, setDay] = useState(Math.round((today - START) / DAY))
  const date = iso(START + day * DAY)
  const seats = useSeats(date)
  const changes = useChanges()
  const { select, selectedId } = useStore()
  const rows = seats.data?.seats ?? []
  const width = 680
  const { points, seatR, height } = useMemo(() => hemicycleLayout(81, width), [])
  const ordered = useMemo(() => [...rows].sort((a, b) => (a.party ?? '~').localeCompare(b.party ?? '~')), [rows])
  const parties = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((r) => m.set(r.party ?? 's/ partido', (m.get(r.party ?? 's/ partido') ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [rows])
  const near = (changes.data ?? []).filter((c) => Math.abs(Date.parse(c.date) - Date.parse(date)) <= 45 * DAY)
  const marks = (changes.data ?? []).map((c) => Math.round((Date.parse(c.date) - START) / DAY))
  return (
    <div className="view">
      <h1>Senado Federal em {fmtDate(date)}</h1>
      <p className="lede">Quem ocupava cada uma das 81 cadeiras na data escolhida, reconstruído a partir dos exercícios de mandato e das filiações publicadas nos Dados Abertos do Senado. Arraste para ver trocas de partido, suplentes assumindo e retornos de titulares.</p>
      <div className="slider-wrap">
        <div className="slider-marks" aria-hidden>
          {marks.map((m, i) => <span key={i} style={{ left: `${(m / Math.round((today - START) / DAY)) * 100}%` }} />)}
        </div>
        <Slider min={0} max={Math.round((today - START) / DAY)} stepSize={1} labelStepSize={365} value={day}
          onChange={setDay} labelRenderer={(v) => new Date(START + v * DAY).getUTCFullYear().toString()} aria-label="Data" />
        <div className="slider-quick">
          {[['1º/02/2023', '2023-02-01'], ['Eleição da Mesa 2025', '2025-02-01'], ['Hoje', iso(today)]].map(([l, d]) => (
            <Tag key={d} interactive minimal onClick={() => setDay(Math.round((Date.parse(d) - START) / DAY))}>{l}</Tag>
          ))}
        </div>
      </div>
      <div className="split">
        <div>
          {seats.isLoading ? <Spinner size={24} /> : (
            <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Hemiciclo do Senado">
              {ordered.map((s: SeatRow, i) => points[i] && (
                <motion.circle key={s.person_id} data-testid="seat" className="seat" layout
                  animate={{ cx: points[i].x, cy: points[i].y, r: s.person_id === selectedId ? seatR * 1.35 : seatR }}
                  transition={{ duration: 0.4 }} fill={partyColor(s.party)}
                  stroke={s.participation === 'suplente' ? '#fff' : 'none'} strokeDasharray="2 1.5" strokeWidth={s.participation === 'suplente' ? 1.2 : 0}
                  onClick={() => select(s.person_id)}>
                  <title>{`${s.name} · ${s.party ?? 's/ partido'}-${s.uf ?? ''}${s.participation === 'suplente' ? ' · suplente em exercício' : ''}`}</title>
                </motion.circle>
              ))}
              <text x={width / 2} y={height - 40} textAnchor="middle" fill="var(--fg-0)" fontSize={28} fontWeight={600}>{seats.data?.observed}</text>
              <text x={width / 2} y={height - 20} textAnchor="middle" fill="var(--fg-2)" fontSize={11}>de 81 cadeiras · contorno = suplente</text>
            </svg>
          )}
          {seats.data?.note && <p className="warn-text">{seats.data.note}</p>}
          <div className="chip-legend">
            {parties.map(([p, n]) => <span key={p}><i style={{ background: partyColor(p) }} />{p} {n}</span>)}
          </div>
        </div>
        <div className="card">
          <h3>Mudanças próximas a esta data</h3>
          {!near.length && <p className="muted">Nenhuma mudança registrada em 45 dias.</p>}
          <ul className="changes">
            {near.slice(0, 40).map((c, i) => (
              <li key={i}><span className="mono">{fmtDate(c.date)}</span> <b>{KIND[c.kind]}</b>{' '}
                <a className="link" onClick={() => select(c.person_id)}>{c.name}</a>{c.uf ? ` (${c.uf})` : ''} — {c.detail}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
