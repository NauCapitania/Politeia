import { useMemo, useState } from 'react'
import { Callout, Spinner } from '@blueprintjs/core'
import { usePres2025 } from '../api/client'
import { hemicycleLayout } from './Hemicycle'
import { partyColor } from '../format'
import { SrcList } from '../components/SrcList'
import { useStore } from '../store'

const CAND_COLOR = ['#4c8dff', '#e5534b', '#d9a400', '#9b7bd6']
const pct = (x: number) => `${Math.round(x * 100)}%`

export function Presidencia2025() {
  const q = usePres2025()
  const { select } = useStore()
  const [focus, setFocus] = useState<string | null>(null)
  const d = q.data
  const cands: string[] = useMemo(() => d?.contest?.result?.map((r: any) => r.candidate) ?? [], [d])
  const color = (c: string) => CAND_COLOR[cands.indexOf(c)] ?? '#888'
  const width = 640
  const layout = useMemo(() => hemicycleLayout(81, width), [])
  if (q.isLoading) return <div className="view"><Spinner size={24} /></div>
  if (!d?.available) return <div className="view"><Callout intent="warning">Dossiê da eleição de 2025 não carregado.</Callout></div>
  const senators = [...d.senators].sort((a: any, b: any) => (a.party ?? '').localeCompare(b.party ?? ''))
  const sel = senators.find((s: any) => s.person_id === focus)
  return (
    <div className="view">
      <h1>{d.contest.title}</h1>
      <Callout intent="warning" icon="eye-off" className="mb">{d.contest.note} <SrcList sources={d.contest_sources} /></Callout>
      <div className="result-bar">
        {d.contest.result.map((r: any) => (
          <div key={r.candidate} style={{ flex: r.votes, background: color(r.candidate) }} title={`${r.candidate}: ${r.votes}`}>
            <b>{r.votes}</b> {r.candidate} <span className="small">({r.party}-{r.uf})</span>
          </div>
        ))}
      </div>
      <p className="small muted">Partidos que anunciaram apoio a {cands[0]} somavam <b>{d.summary.declared_support_seats}</b> senadores; ele teve <b>{d.summary.votes[cands[0]]}</b> votos. Soma das probabilidades do modelo: {Object.entries(d.summary.expected_check).map(([k, v]) => `${k} ${Number(v).toFixed(1)}`).join(' · ')}.</p>
      <div className="split">
        <div>
          <h3>Probabilidade estimada de voto (inferência)</h3>
          <svg viewBox={`0 0 ${width} ${layout.height}`} width="100%" role="img" aria-label="Probabilidades por senador">
            {senators.map((s: any, i: number) => {
              const p = layout.points[i]
              if (!p) return null
              const top = s.most_likely
              const conf = s.posterior[top]
              return (
                <g key={s.person_id} onClick={() => setFocus(s.person_id)} style={{ cursor: 'pointer' }} data-testid="seat">
                  <circle cx={p.x} cy={p.y} r={layout.seatR} fill={color(top)} opacity={0.25 + 0.75 * conf}
                    stroke={focus === s.person_id ? 'var(--fg-0)' : partyColor(s.party)} strokeWidth={focus === s.person_id ? 2 : 1.5} />
                  <title>{`${s.name} (${s.party}) · ${cands.map((c) => `${c}: ${pct(s.posterior[c])}`).join(' · ')}`}</title>
                </g>
              )
            })}
          </svg>
          <div className="chip-legend">{cands.map((c) => <span key={c}><i style={{ background: color(c) }} />{c}</span>)}<span className="muted">opacidade = probabilidade · contorno = partido</span></div>
          <h3>Apoio partidário × cadeiras</h3>
          <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Partido</th><th>Senadores</th><th>Apoio declarado</th><th>Votos esperados</th><th>Fontes</th></tr></thead>
            <tbody>
              {d.parties.map((p: any) => (
                <tr key={p.party}>
                  <td><i className="party-dot" style={{ background: partyColor(p.party) }} />{p.party}</td>
                  <td>{p.senators}</td>
                  <td>{p.support ? `${p.support.candidate}${p.support.support === 'split' ? ' (dividido)' : ''}` : '—'}</td>
                  <td className="small">{p.expected_votes ? Object.entries(p.expected_votes).map(([c, v]) => `${c.split(' ').pop()} ${Number(v).toFixed(1)}`).join(' · ') : ''}</td>
                  <td><SrcList sources={p.support_sources} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
        <div className="card">
          {!sel && <p className="muted">Clique num senador para ver a probabilidade e a justificativa.</p>}
          {sel && (
            <>
              <h3><a className="link" onClick={() => select(sel.person_id)}>{sel.name}</a> <span className="muted">{sel.party}-{sel.uf}</span></h3>
              {cands.map((c) => (
                <div key={c} className="prob-row">
                  <span>{c}</span>
                  <div className="prob-track"><div style={{ width: pct(sel.posterior[c]), background: color(c) }} /></div>
                  <b>{pct(sel.posterior[c])}</b>
                  <span className="small muted">a priori {pct(sel.prior[c])}</span>
                </div>
              ))}
              <h4>Por quê</h4>
              <ul>{sel.justification.map((j: any, i: number) => <li key={i}><span className={`kind kind-${j.kind}`}>{j.kind === 'analysis' ? 'Hipótese' : j.kind === 'official' ? 'Oficial' : j.kind === 'declaration' ? 'Declaração' : 'Imprensa'}</span> {j.text} <SrcList sources={j.sources} hidePress /></li>)}</ul>
            </>
          )}
          <h4>Método</h4>
          <p className="small">{d.model.method}</p>
          <ul className="small">{d.model.caveats.map((c: string) => <li key={c}>{c}</li>)}</ul>
          <SrcList sources={d.model_sources} />
        </div>
      </div>
    </div>
  )
}
