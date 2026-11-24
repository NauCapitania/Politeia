import { useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { Slider, Spinner, Tag } from '@blueprintjs/core'
import { isStatic, useChanges, useSeats, useSeats2027, useSnapshotMeta, type SeatRow } from '../api/client'
import { hemicycleLayout } from './Hemicycle'
import { partyColor, fmtDate } from '../format'
import { useStore } from '../store'

const START = Date.UTC(2023, 1, 1)
const DAY = 86400000
const iso = (t: number) => new Date(t).toISOString().slice(0, 10)
const KIND: Record<string, string> = { exercicio_inicio: 'Assume', exercicio_fim: 'Sai', troca_partido: 'Troca de partido' }

export function Senado() {
  const today = Math.floor(Date.now() / DAY) * DAY
  const { data: snapshot, isPending: snapshotPending, isError: snapshotError } = useSnapshotMeta()
  const dates = snapshot?.composition_dates
  const staticMode = isStatic()
  const last = staticMode ? (dates?.length ?? 1) - 1 : Math.round((today - START) / DAY)
  const [selected, setDay] = useState<number>()
  const day = selected ?? last
  const date = staticMode ? dates?.[day] : iso(START + day * DAY)
  const [future, setFuture] = useState(false)
  const current = useSeats(date)
  const proj = useSeats2027(future)
  const seats = future ? proj : current
  const changes = useChanges()
  const { select, selectedId } = useStore()
  const rows: SeatRow[] = seats.data?.seats ?? []
  const width = 680
  const { points, seatR, height } = useMemo(() => hemicycleLayout(81, width), [])
  const ordered = useMemo(() => [...rows].sort((a, b) => (a.party ?? '~').localeCompare(b.party ?? '~')), [rows])
  const parties = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((r) => m.set(r.party ?? 's/ partido', (m.get(r.party ?? 's/ partido') ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [rows])
  const near = date ? (changes.data ?? []).filter((c) => Math.abs(Date.parse(c.date) - Date.parse(date)) <= 45 * DAY) : []
  const marks = (changes.data ?? []).map((c) => staticMode ? dates?.indexOf(c.date) ?? -1 : Math.round((Date.parse(c.date) - START) / DAY))
    .filter((m) => m >= 0 && m <= last)
  const lastDate = staticMode ? dates?.at(-1) : iso(today)
  const quickDates = [['1º/02/2023', '2023-02-01'], ['Eleição da Mesa 2025', '2025-02-01'],
    [staticMode ? 'Data do snapshot' : 'Hoje', lastDate]]
  return (
    <div className="view">
      <div className="mode-switch">
        <Tag interactive minimal={future} intent={future ? 'none' : 'primary'} onClick={() => setFuture(false)}>{staticMode ? 'Histórico até o snapshot' : 'Histórico até hoje'}</Tag>
        <Tag interactive minimal={!future} intent={future ? 'primary' : 'none'} onClick={() => setFuture(true)}>Senado a partir de 1º/02/2027</Tag>
      </div>
      {future ? <h1>Senado Federal a partir de 1º/02/2027</h1> : <h1>Senado Federal{date ? ` em ${fmtDate(date)}` : ''}</h1>}
      {future ? (
        <p className="lede">Em 2026 foram eleitos 54 senadores (2/3 das cadeiras) para mandatos até 2035. As outras 27 cadeiras seguem até 2031. Contorno tracejado = eleito em 2026; contorno sólido = reeleito.</p>
      ) : <p className="lede">Quem ocupava cada uma das 81 cadeiras na data escolhida, reconstruído a partir dos exercícios de mandato e das filiações publicadas nos Dados Abertos do Senado. {staticMode ? 'O snapshot traz a composição em datas-chave.' : 'Arraste para ver trocas de partido, suplentes assumindo e retornos de titulares.'}</p>}
      {!future && date && last > 0 && <div className={staticMode ? 'slider-wrap snapshot-slider' : 'slider-wrap'}>
        <div className="slider-marks" aria-hidden>
          {marks.map((m, i) => <span key={i} style={{ left: `${(m / last) * 100}%` }} />)}
        </div>
        <Slider min={0} max={last} stepSize={1} labelStepSize={staticMode ? Math.max(1, Math.ceil(last / 4)) : 365} value={day}
          onChange={setDay} labelRenderer={(v) => staticMode ? fmtDate(dates?.[v]) : new Date(START + v * DAY).getUTCFullYear().toString()} aria-label="Data" />
        <div className="slider-quick">
          {quickDates.map(([label, d]) => {
            const index = d ? staticMode ? dates?.indexOf(d) ?? -1 : Math.round((Date.parse(d) - START) / DAY) : -1
            return index < 0 ? null : <Tag key={label} interactive minimal onClick={() => setDay(index)}>{label}</Tag>
          })}
        </div>
      </div>}
      <div className="split">
        <div>
          {!future && staticMode && snapshotError ? <p className="warn-text">Histórico do snapshot indisponível.</p>
            : seats.isLoading || (!future && staticMode && snapshotPending) ? <Spinner size={24} /> : (
            <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Hemiciclo do Senado">
              {ordered.map((s: SeatRow, i) => points[i] && (
                <motion.circle key={s.person_id ?? `${s.name}-${s.uf}`} data-testid="seat" className="seat" layout
                  animate={{ cx: points[i].x, cy: points[i].y, r: s.person_id === selectedId ? seatR * 1.35 : seatR }}
                  transition={{ duration: 0.4 }} fill={partyColor(s.party)}
                  stroke={outline(s) ? '#fff' : 'none'} strokeDasharray={outline(s) === 'dash' ? '2 1.5' : undefined}
                  strokeWidth={outline(s) ? 1.2 : 0}
                  onClick={() => s.person_id && select(s.person_id)}>
                  <title>{`${s.name} · ${s.party ?? 's/ partido'}-${s.uf ?? ''}${label(s)}`}</title>
                </motion.circle>
              ))}
              <text x={width / 2} y={height - 40} textAnchor="middle" fill="var(--fg-0)" fontSize={28} fontWeight={600}>{seats.data?.observed}</text>
              <text x={width / 2} y={height - 20} textAnchor="middle" fill="var(--fg-2)" fontSize={11}>{future ? 'de 81 cadeiras · posse em 1º/02/2027' : 'de 81 cadeiras · contorno = suplente'}</text>
            </svg>
          )}
          {seats.data?.note && <p className="warn-text">{seats.data.note}</p>}
          <div className="chip-legend">
            {parties.map(([p, n]) => <span key={p}><i style={{ background: partyColor(p) }} />{p} {n}</span>)}
          </div>
        </div>
        {future ? <Future2027 data={seats.data} /> : <div className="card">
          <h3>Mudanças próximas a esta data</h3>
          {!near.length && <p className="muted">Nenhuma mudança registrada em 45 dias.</p>}
          <ul className="changes">
            {near.slice(0, 40).map((c, i) => (
              <li key={i}><span className="mono">{fmtDate(c.date)}</span> <b>{KIND[c.kind]}</b>{' '}
                <a className="link" onClick={() => select(c.person_id)}>{c.name}</a>{c.uf ? ` (${c.uf})` : ''} — {c.detail}</li>
            ))}
          </ul>
        </div>}
      </div>
    </div>
  )
}

const outline = (s: any) => s.group === 'eleito_2026' ? 'dash' : s.group === 'reeleito' ? 'solid' : s.participation === 'suplente' ? 'dash' : null
const label = (s: any) => s.group === 'eleito_2026' ? ' · eleito em 2026' : s.group === 'reeleito' ? ' · reeleito em 2026'
  : s.group === 'continua' ? ' · mandato até 2031' : s.participation === 'suplente' ? ' · suplente em exercício' : ''

function Future2027({ data }: { data?: any }) {
  const select = useStore((s) => s.select)
  if (!data) return <Spinner size={20} />
  const elected = data.seats.filter((s: any) => s.group !== 'continua').sort((a: any, b: any) => a.uf.localeCompare(b.uf))
  return (
    <div className="card">
      <h3>Renovação de 2/3</h3>
      <div className="facts">
        <span><b>{data.continuing}</b> <span className="faint">seguem até 2031</span></span>
        <span><b>{data.elected}</b> <span className="faint">eleitos em 2026</span></span>
        <span><b>{data.reelected}</b> <span className="faint">reeleitos</span></span>
      </div>
      <p className="warn-text">{data.note}</p>
      <ul className="changes">
        {elected.map((s: any) => (
          <li key={`${s.uf}-${s.name}`}><span className="mono">{s.uf}</span>{' '}
            {s.person_id ? <a className="link" onClick={() => select(s.person_id)}>{s.name}</a> : <b>{s.name}</b>}
            {' '}({s.party}){s.group === 'reeleito' ? ' — reeleito' : ''}</li>
        ))}
      </ul>
    </div>
  )
}
