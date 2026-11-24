import { useMemo, useState } from 'react'
import { Callout, Spinner, Tag } from '@blueprintjs/core'
import { useDossier, useNews } from '../api/client'
import { fmtDate, fmtDateTime } from '../format'
import { SrcList } from '../components/SrcList'

const REPORT: Record<string, { label: string; color: string }> = {
  sent_to_pgr: { label: 'Relatório enviado à PGR', color: '#e5534b' },
  archived: { label: 'Relatório arquivado', color: '#6c7a89' },
  not_reported: { label: 'Sem relatório citado', color: '#3a4552' },
}
const TRACK: Record<string, string> = { caso: 'Caso Master', stf: 'STF', senado: 'Senado' }
const STATUS: Record<string, string> = { official_reported: 'Ato oficial (reportado)', fact_reported: 'Fato reportado', press_report: 'Reportagem' }

export function Stf() {
  const q = useDossier('stf-caso-master')
  const news = useNews('caso_master')
  const [focus, setFocus] = useState<string | null>(null)
  const [track, setTrack] = useState('')
  const width = 520
  const layout = useMemo(() => {
    const r = width / 2 - 40
    const points = Array.from({ length: 11 }, (_, i) => {
      const a = Math.PI - (Math.PI * i) / 10
      return { x: width / 2 + r * Math.cos(a), y: r + 24 - r * Math.sin(a) }
    })
    return { points, seatR: 17, height: r + 60 }
  }, [])
  const d = q.data
  if (q.isLoading) return <div className="view"><Spinner size={24} /></div>
  if (!d) return <div className="view"><Callout intent="warning">Dossiê STF / caso Master não carregado.</Callout></div>
  const it = d.items
  const seats = [...it.minister, ...(it.vacancy ?? [])].sort((a: any, b: any) => Number(a.seat) - Number(b.seat))
  const sel = seats.find((m: any) => m.id === focus)
  const status = it.current_status?.[0]
  const timeline = [...it.timeline_event].filter((t: any) => !track || t.track === track).sort((a: any, b: any) => b.date.localeCompare(a.date))
  const days = status ? Math.ceil((Date.parse(status.deadline_estimate) - Date.now()) / 86400000) : null
  return (
    <div className="view">
      <h1>STF e caso Master</h1>
      <Callout intent="warning" icon="disable" className="mb">{d.items.disclaimer?.[0]?.text ?? 'Menção em relatório ou reportagem não é prova de ilícito. O Politeia distingue fato oficial, cobertura jornalística, alegação e análise.'}</Callout>
      {status && (
        <div className="card mb status-card">
          <div>
            <div className="insp-kind">Agora</div>
            <h3>{status.title}</h3>
            <p className="small">Recebidos em {fmtDate(status.received_on)} · {status.responsible}</p>
            <p className="small">Prazo de {status.deadline_days} dias: estimado para <b>{fmtDate(status.deadline_estimate)}</b>{days != null && (days >= 0 ? ` (faltam ${days} dias)` : ' (prazo estimado vencido)')}. {status.deadline_note}</p>
            <SrcList sources={status.sources} />
          </div>
          <div>
            <div className="insp-kind">O que a PGR pode fazer</div>
            {status.possible_outcomes.map((o: any) => <div key={o.outcome} className="row"><b>{o.outcome}</b> → <span className="small">{o.then}</span></div>)}
          </div>
        </div>
      )}
      <div className="split">
        <div>
          <h3>Plenário do STF — 11 cadeiras</h3>
          <svg viewBox={`0 0 ${width} ${layout.height}`} width="100%" role="img" aria-label="Ministros do STF">
            {seats.map((m: any, i: number) => {
              const p = layout.points[i]
              const r = m.master_report ? REPORT[m.master_report.status] : null
              return (
                <g key={m.id} data-testid="minister" onClick={() => setFocus(m.id)} style={{ cursor: 'pointer' }}>
                  <circle cx={p.x} cy={p.y} r={layout.seatR} fill={r?.color ?? 'transparent'} stroke={focus === m.id ? 'var(--fg-0)' : r ? 'none' : 'var(--line-strong)'}
                    strokeDasharray={r ? undefined : '3 2'} strokeWidth={focus === m.id ? 2.5 : 1.5} />
                  <text x={p.x} y={p.y + layout.seatR + 13} textAnchor="middle" fontSize={10} fill="var(--fg-1)">{m.name.split(' ').slice(-1)[0]}</text>
                  <title>{m.name}</title>
                </g>
              )
            })}
          </svg>
          <div className="chip-legend">{Object.values(REPORT).map((r) => <span key={r.label}><i style={{ background: r.color }} />{r.label}</span>)}<span><i className="hollow" />Vaga aberta</span></div>
          {sel && (
            <div className="card">
              <h3>{sel.name} <span className="muted small">{sel.role ?? ''}</span></h3>
              {sel.full_name && <div className="muted small">{sel.full_name}</div>}
              {sel.previous && <p>Vaga de {sel.previous}</p>}
              {sel.nominated_by && <p className="small">Indicado por <b>{sel.nominated_by}</b> · posse em {fmtDate(sel.took_office)}{sel.took_office_note ? ` (${sel.took_office_note})` : ''}</p>}
              {sel.master_report && <p><Tag minimal style={{ background: REPORT[sel.master_report.status].color }}>{REPORT[sel.master_report.status].label}</Tag> <span className="small">{sel.master_report.label}</span></p>}
              {sel.plenary_2026_09_15 && <p className="small">Sessão de 15/09/2026 (questão de ordem): votou pela <b>{sel.plenary_2026_09_15}</b></p>}
              <ul className="small">{(sel.notes ?? []).map((n: string) => <li key={n}>{n}</li>)}</ul>
              <SrcList sources={sel.sources} />
            </div>
          )}
        </div>
        <div>
          <h3>Quem decide o quê</h3>
          {it.procedure_actor.sort((a: any, b: any) => a.order - b.order).map((a: any) => (
            <div key={a.id} className="card mb flow-step"><b>{a.actor}</b><p className="small">{a.powers}</p><SrcList sources={a.sources} /></div>
          ))}
          <h3>Impeachment de ministro no Senado</h3>
          <ol className="steps">
            {it.impeachment_step.sort((a: any, b: any) => a.order - b.order).map((s: any) => (
              <li key={s.id}><b>{s.step}</b><p className="small">{s.text}</p><SrcList sources={s.sources} /></li>
            ))}
          </ol>
        </div>
      </div>
      <h3>Linha do tempo</h3>
      <div className="toolbar">{[['', 'Tudo'], ...Object.entries(TRACK)].map(([k, l]) => <Tag key={k} interactive minimal={track !== k} intent={track === k ? 'primary' : 'none'} onClick={() => setTrack(k)}>{l}</Tag>)}</div>
      <ol className="timeline master-timeline">
        {timeline.map((t: any) => (
          <li key={t.id}>
            <span className="mono">{fmtDate(t.date)}</span>
            <span className="kind">{TRACK[t.track]}</span>
            <span className="grow">{t.text} <span className="small muted">· {STATUS[t.status] ?? t.status}</span> <SrcList sources={t.sources} /></span>
          </li>
        ))}
      </ol>
      <h3>Últimas notícias sobre o caso</h3>
      {news.data?.slice(0, 12).map((n: any) => (
        <div key={n.id} className="row"><a className="link" href={n.url} target="_blank" rel="noreferrer">{n.title}</a> <span className="small muted">{n.outlet} · {fmtDateTime(n.published_at)}</span></div>
      ))}
    </div>
  )
}
