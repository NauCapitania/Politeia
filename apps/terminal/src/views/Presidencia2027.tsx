import { Callout, Spinner } from '@blueprintjs/core'
import { usePres2027 } from '../api/client'
import { partyColor } from '../format'
import { Badge, SrcList } from '../components/SrcList'
import { useStore } from '../store'

const STANCE: Record<string, string> = {
  favoravel_andamento: 'Favorável a dar andamento', contrario: 'Contrário', sem_declaracao: 'Sem declaração pública', ambiguo: 'Ambíguo',
}

export function Presidencia2027() {
  const q = usePres2027()
  const { select } = useStore()
  const d = q.data
  if (q.isLoading) return <div className="view"><Spinner size={24} /></div>
  if (!d?.available) return <div className="view"><Callout intent="warning">Dossiê da eleição de 2027 não carregado.</Callout></div>
  const c = d.contest[0]
  return (
    <div className="view">
      <h1>{c.title}</h1>
      <Callout intent="primary" icon="info-sign" className="mb">{c.note} Maioria absoluta: {c.majority} de {c.voters} votos. <SrcList sources={c.sources} /></Callout>
      <h3>Candidatos potenciais</h3>
      <div className="cards">
        {d.candidate.map((k: any) => (
          <div key={k.id} className="card">
            <h3><a className="link" onClick={() => k.person_id && select(k.person_id)}>{k.name}</a> <span className="party-pill" style={{ background: partyColor(k.party) }}>{k.party}</span> <span className="muted">{k.uf}</span></h3>
            <div className="small muted">{k.status}</div>
            <p><b>Impeachment de ministro do STF:</b> {STANCE[k.impeachment_stance] ?? k.impeachment_stance}</p>
            <p className="small">{k.impeachment_note}</p>
            <SrcList sources={k.sources} hidePress />
          </div>
        ))}
      </div>
      <h3>Cenários de votos (intervalos, não previsão)</h3>
      {d.scenarios.map((s: any) => (
        <div key={s.id}>
          <p className="small muted">{s.note}</p>
          {s.scenarios.map((sc: any) => (
            <div key={sc.name} className="card mb">
              <h4>{sc.name}</h4>
              {sc.candidates.map((k: any) => (
                <div key={k.name} className="range-row">
                  <span>{k.name}</span>
                  <div className="range-track">
                    <div className="range" style={{ left: `${(k.low / 81) * 100}%`, width: `${((k.high - k.low) / 81) * 100}%` }} />
                    <div className="majority" style={{ left: `${(41 / 81) * 100}%` }} title="41 votos" />
                  </div>
                  <b>{k.low}–{k.high}</b>
                  <div className="small muted">{k.basis}</div>
                </div>
              ))}
            </div>
          ))}
          <SrcList sources={s.sources} />
        </div>
      ))}
      <h3>Composição projetada para 2027</h3>
      <p className="small muted">Fontes divergem; o Politeia mostra as duas em vez de escolher.</p>
      <div className="cards">
        {d.party_composition.map((pc: any) => {
          const entries = Object.entries(pc.parties as Record<string, number>).sort((a, b) => b[1] - a[1])
          const known = entries.reduce((t, [, n]) => t + n, 0)
          const missing = Math.max(0, c.voters - known)
          return (
            <div key={pc.id} className="card">
              <h4>{pc.label}</h4>
              <div className="stack-bar">{entries.map(([p, n]) => <div key={p} style={{ flex: n, background: partyColor(p) }} title={`${p}: ${n}`}>{n >= 3 ? p : ''}</div>)}
                {missing > 0 && <div style={{ flex: missing, background: 'var(--bg-3)', color: 'var(--fg-2)' }} title={`Não informado pela fonte: ${missing}`}>{missing >= 10 ? 'não informado' : ''}</div>}</div>
              <div className="chip-legend">{entries.map(([p, n]) => <span key={p}><i style={{ background: partyColor(p) }} />{p} {n}</span>)}{missing > 0 && <span className="muted">não informado pela fonte: {missing} de {c.voters}</span>}</div>
              <p className="small muted">{pc.note}</p>
              <SrcList sources={pc.sources} />
            </div>
          )
        })}
      </div>
      <h3>Declarações registradas</h3>
      {d.claims.map((cl: any) => (
        <div key={cl.id} className="row"><Badge kind={cl.claim_type} /> <b>{cl.subject_label}</b>: {cl.statement} <span className="small muted">({cl.stated_on})</span> <SrcList sources={cl.sources} /></div>
      ))}
      <h3>Eleitos em 2026 (mandato 2027–2035)</h3>
      <div className="vote-grid">
        {d.elected_2026.map((e: any) => (
          <button key={e.id} className="vote-chip" onClick={() => e.person_id && select(e.person_id)} disabled={!e.person_id}>
            <i style={{ background: partyColor(e.party) }} />{e.name} <span className="muted">{e.party}-{e.uf}</span>{!e.person_id && <span className="small muted"> · novo</span>}
          </button>
        ))}
      </div>
    </div>
  )
}
