import { Button, Spinner, Tab, Tabs } from '@blueprintjs/core'
import { useSenator } from '../api/client'
import { useStore } from '../store'
import { fmtDate, partyColor } from '../format'
import { Badge, SrcList } from './SrcList'

const VOTE: Record<string, string> = { Sim: 'Sim', Não: 'Não', Abstenção: 'Abstenção', Votou: 'Votou (secreta)', 'P-NRV': 'Presente, não votou' }

export function SenatorPanel({ id }: { id: string }) {
  const { select } = useStore()
  const q = useSenator(id)
  const d = q.data
  return (
    <aside className="inspector" aria-label="Perfil do senador">
      <div className="insp-head"><span className="insp-kind">Perfil</span><Button minimal size="small" icon="cross" aria-label="Fechar" onClick={() => select(null)} /></div>
      {q.isLoading && <Spinner size={20} />}
      {d && (
        <div className="profile">
          <div className="profile-id">
            {d.photo_url && <img src={d.photo_url} alt={d.name} />}
            <div>
              <h2>{d.name}</h2>
              <div className="muted">{d.full_name}</div>
              {d.parties[0] && <span className="party-pill" style={{ background: partyColor(d.parties[0].party) }}>{d.parties[0].party}</span>}
              {d.mandates[0]?.uf && <span className="muted"> {d.mandates[0].uf}</span>}
              <div><a className="link" href={d.links.perfil_oficial} target="_blank" rel="noreferrer">Perfil oficial e redes sociais ↗</a></div>
            </div>
          </div>
          <Tabs id="perfil" renderActiveTabPanelOnly>
            <Tab id="mandato" title="Mandato" panel={<div>
              <h4>Mandatos</h4>
              {d.mandates.map((m: any) => <div key={m.id} className="row">{m.uf} · {m.source_participation ?? m.participation} · {fmtDate(m.start)} – {fmtDate(m.end)}{m.holder && m.participation !== 'holder' ? ` · titular: ${m.holder}` : ''}</div>)}
              <h4>Exercícios</h4>
              {d.exercises.map((e: any, i: number) => <div key={i} className="row">{fmtDate(e.start)} – {e.end ? fmtDate(e.end) : 'atual'}{e.end_cause ? ` · ${e.end_cause}` : ''}</div>)}
              <h4>Partidos</h4>
              {d.parties.filter((p: any) => p.basis === 'affiliation_history').map((p: any, i: number) => <div key={i} className="row"><span className="party-dot" style={{ background: partyColor(p.party) }} />{p.party} · {fmtDate(p.from)} – {p.to ? fmtDate(p.to) : 'atual'}</div>)}
              <p className="muted small">{d.social_note}</p>
            </div>} />
            <Tab id="votos" title={`Votos (${Object.values(d.vote_summary).reduce((a: number, b: any) => a + b, 0)})`} panel={<div>
              <div className="row">{Object.entries(d.vote_summary).map(([k, v]) => <span key={k} className="stat">{VOTE[k] ?? k}: <b>{String(v)}</b></span>)}</div>
              {d.votes.map((v: any) => <div key={v.id} className="row vote-row"><span className="mono">{fmtDate(v.date)}</span> <b>{VOTE[v.vote] ?? v.vote_label}</b>{v.secret ? ' · secreta' : ''}<div className="small">{v.description}</div></div>)}
            </div>} />
            <Tab id="discursos" title="Discursos" panel={<div>
              {d.speeches.map((s: any) => <div key={s.id} className="row"><span className="mono">{fmtDate(s.date)}</span> {s.kind} <a className="link" href={s.url} target="_blank" rel="noreferrer">texto ↗</a><div className="small">{s.summary}</div></div>)}
            </div>} />
            <Tab id="noticias" title={`Notícias (${d.news.length})`} panel={<div>
              {!d.news.length && <p className="muted">Nenhuma notícia recente cita o nome completo deste senador.</p>}
              {d.news.map((n: any) => <div key={n.id} className="row"><a className="link" href={n.url} target="_blank" rel="noreferrer">{n.title}</a><div className="small muted">{n.outlet} · {fmtDate(n.published_at)}</div></div>)}
            </div>} />
            <Tab id="posicoes" title="Posições" panel={<div>
              {!d.claims.length && <p className="muted">Nenhuma posição registrada com fonte. Ausência de registro não significa oposição.</p>}
              {d.claims.map((c: any) => <div key={c.id} className="row"><Badge kind={c.claim_type} /> {c.statement}<div><SrcList sources={c.sources} /></div></div>)}
            </div>} />
          </Tabs>
        </div>
      )}
    </aside>
  )
}
