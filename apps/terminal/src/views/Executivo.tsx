import { useMemo, useState } from 'react'
import { Button, Callout, Spinner } from '@blueprintjs/core'
import { fmtDate, fmtDateTime, partyColor } from '../format'
import { SrcList } from '../components/SrcList'
import { InstitutionMasthead } from '../components/InstitutionMasthead'
import { CabinetTimeline } from './executivo/CabinetTimeline'
import { KIND_LABEL, partyCounts, shortName, useExecutivo, useExecutivoGuide, type Body, type Kind } from './executivo/data'
import './executivo/executivo.css'

type Tab = 'estrutura' | 'linha' | 'poderes' | 'fontes'
const TABS: { id: Tab; label: string }[] = [
  { id: 'estrutura', label: 'Estrutura e ministros' },
  { id: 'linha', label: 'Linha do tempo do gabinete' },
  { id: 'poderes', label: 'Como funciona' },
  { id: 'fontes', label: 'Fontes' },
]
const KIND_ORDER: Kind[] = ['presidencia', 'ministerio', 'orgao_ministerial', 'entidade']
const LINK_LABEL: Record<string, string> = { congresso: 'Congresso', senado: 'Senado', stf: 'STF', tcu: 'TCU', ministerios: 'Ministérios' }

function Holder({ body }: { body: Body }) {
  const h = body.holder
  if (!h) return <div className="h muted">Sem titular listado</div>
  return (
    <div className="h">
      <span className="party-dot" style={{ background: partyColor(h.party) }} />
      {h.name}{h.interim ? ' (interino/a)' : ''} <span className="muted">{h.party ?? 'sem partido'}{h.uf ? `/${h.uf}` : ''}</span>
    </div>
  )
}

function Detail({ body }: { body: Body }) {
  const [all, setAll] = useState(false)
  const entities = all ? body.entities : body.entities.slice(0, 12)
  return (
    <div className="card exe-detail" data-testid="exe-detail">
      <div className="insp-kind">{KIND_LABEL[body.kind]}{body.acronym ? ` · ${body.acronym}` : ''}</div>
      <h3>{body.name}</h3>
      <Holder body={body} />
      {body.holder?.senate_person_id && <p className="small muted">Também tem mandato no Senado registrado no Politeia.</p>}
      <h4>Titulares desde 2023</h4>
      {body.terms.length ? body.terms.slice().reverse().map((t) => (
        <div key={t.id} className="row">
          <span className="party-dot" style={{ background: partyColor(t.party) }} />
          {t.profile_url ? <a href={t.profile_url} target="_blank" rel="noreferrer">{t.name}</a> : t.name}
          {t.interim ? ' (interino/a)' : ''} <span className="muted small">{t.party ?? 'sem partido'}{t.uf ? `/${t.uf}` : ''} · {fmtDate(t.start)} – {t.end ? fmtDate(t.end) : 'em exercício'}</span>
        </div>
      )) : <p className="small muted">Nenhum titular na lista do gabinete.</p>}
      {body.competence && (<><h4>Competências (SIORG)</h4><div className="exe-competence">{body.competence}</div></>)}
      {!body.competence && body.purpose && (<><h4>Finalidade (SIORG)</h4><div className="exe-competence">{body.purpose}</div></>)}
      {body.legal_basis && <p className="small"><b>Base legal:</b> {body.legal_basis}</p>}
      <p className="small muted">{body.administrative_units} unidades internas no SIORG{body.site ? <> · <a href={body.site} target="_blank" rel="noreferrer">site oficial</a></> : null}</p>
      {body.entities.length > 0 && (
        <>
          <h4>Entidades vinculadas ({body.entities.length})</h4>
          {entities.map((e) => (
            <div key={e.code} className="row small">{e.name}{e.acronym ? ` (${e.acronym})` : ''} <span className="muted">· {e.legal_nature ?? '—'}{e.direct ? '' : ' · vinculação indireta'}</span></div>
          ))}
          {body.entities.length > 12 && <Button minimal small onClick={() => setAll(!all)} text={all ? 'Mostrar menos' : `Mostrar todas (${body.entities.length})`} />}
        </>
      )}
    </div>
  )
}

export function Executivo() {
  const q = useExecutivo()
  const guide = useExecutivoGuide()
  const [tab, setTab] = useState<Tab>('estrutura')
  const [sel, setSel] = useState<string | null>(null)
  const [term, setTerm] = useState('')
  const d = q.data
  const groups = useMemo(() => {
    const t = term.trim().toLocaleLowerCase('pt-BR')
    const bodies = (d?.bodies ?? []).filter((b) => !t || [b.name, b.acronym, b.holder?.name, b.holder?.party].some((v) => v?.toLocaleLowerCase('pt-BR').includes(t)))
    return KIND_ORDER.map((k) => ({ kind: k, bodies: bodies.filter((b) => b.kind === k) })).filter((g) => g.bodies.length)
  }, [d, term])
  if (q.isLoading) return <div className="view"><Spinner size={24} /></div>
  if (!d) return <div className="view"><h1>Poder Executivo</h1><Callout intent="warning">Dados do Poder Executivo ainda não carregados.</Callout></div>
  const it = guide.data?.items ?? {}
  const selected = d.bodies.find((b) => b.code === sel) ?? d.bodies.find((b) => b.kind === 'ministerio') ?? d.bodies[0]
  const parties = partyCounts(d.bodies)
  const inOffice = parties.reduce((a, p) => a + p.n, 0)
  const changes = d.bodies.reduce((a, b) => a + Math.max(0, b.terms.length - 1), 0)
  const powers: Record<string, any[]> = {}
  for (const p of it.power ?? []) (powers[p.group] ??= []).push(p)
  return (
    <div className="view">
      <InstitutionMasthead kind="executivo" eyebrow="GOVERNO FEDERAL · PRESIDÊNCIA E MINISTÉRIOS" title="Poder Executivo" subtitle="Da decisão à execução. Pessoas, estruturas e políticas públicas." />
      <p className="lede">{it.overview?.[0]?.text ?? 'Presidência da República, ministérios e entidades da administração federal, com quem ocupa cada pasta.'}</p>
      <div className="exe-kpis">
        <div className="exe-kpi"><b>{d.counts.ministries}</b><span>ministérios</span></div>
        <div className="exe-kpi"><b>{d.counts.top_level - d.counts.ministries}</b><span>outros órgãos ligados à Presidência</span></div>
        <div className="exe-kpi"><b>{d.counts.entities}</b><span>autarquias, fundações e estatais vinculadas</span></div>
        <div className="exe-kpi"><b>{d.counts.ministers_in_office}</b><span>titulares em exercício</span></div>
        <div className="exe-kpi"><b>{changes}</b><span>trocas de titular desde 2023</span></div>
      </div>
      {it.office && (
        <div className="exe-offices">
          {it.office.map((o: any) => (
            <div key={o.id} className="card">
              <div className="insp-kind">{o.role}</div>
              <h3><span className="party-dot" style={{ background: partyColor(o.party) }} />{o.name} <span className="muted small">{o.party} · desde {fmtDate(o.since)}</span></h3>
              <p className="small">{o.rule}</p>
              <SrcList sources={o.sources} hidePress />
            </div>
          ))}
        </div>
      )}
      <div className="exe-tabs" role="tablist">
        {TABS.map((t) => <Button key={t.id} role="tab" aria-selected={tab === t.id} active={tab === t.id} small onClick={() => setTab(t.id)} text={t.label} />)}
      </div>

      {tab === 'estrutura' && (
        <div className="exe-layout">
          <div>
            <div className="card mb">
              <h4>Partidos dos titulares em exercício ({inOffice})</h4>
              <div className="exe-partybar" aria-label="Partidos dos ministros">
                {parties.map((p) => <div key={p.party ?? '-'} title={`${p.party ?? 'Sem partido'}: ${p.n}`} style={{ width: `${(p.n / inOffice) * 100}%`, background: partyColor(p.party) }} />)}
              </div>
              <div className="chip-legend">{parties.map((p) => <span key={p.party ?? '-'}><i style={{ background: partyColor(p.party) }} />{p.party ?? 'Sem partido'} {p.n}</span>)}</div>
            </div>
            <input className="bp5-input mb" placeholder="Filtrar por pasta, sigla, ministro ou partido" value={term} onChange={(e) => setTerm(e.target.value)} style={{ width: '100%' }} />
            {groups.map((g) => (
              <div key={g.kind} className="exe-group">
                <h4>{KIND_LABEL[g.kind]} ({g.bodies.length})</h4>
                <div className="exe-grid">
                  {g.bodies.map((b) => (
                    <button key={b.code} type="button" data-testid="exe-body" className={`exe-body${selected?.code === b.code ? ' sel' : ''}`}
                      style={{ borderLeftColor: partyColor(b.holder?.party) }} onClick={() => setSel(b.code)}>
                      <div className="n">{shortName(b)}</div>
                      <Holder body={b} />
                      <div className="m">{b.acronym ?? ''}{b.entities.length ? ` · ${b.entities.length} vinculadas` : ''}{b.terms.length > 1 ? ` · ${b.terms.length} titulares` : ''}</div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {selected && <Detail body={selected} />}
        </div>
      )}

      {tab === 'linha' && (
        <div className="card">
          <p className="small muted">Cada barra é um titular; a cor é o partido e o hachurado indica interinidade. Clique numa pasta para ver os detalhes na aba de estrutura.</p>
          <CabinetTimeline bodies={d.bodies} selected={sel} onSelect={(c) => { setSel(c); setTab('estrutura') }} />
          {d.unmatched.length > 0 && (
            <>
              <h4>Pastas extintas ou fora do SIORG atual</h4>
              {d.unmatched.map((u) => <div key={u.title} className="row small"><b>{u.ministry}</b> — {u.terms.map((t) => `${t.name} (${fmtDate(t.start)} – ${t.end ? fmtDate(t.end) : 'em exercício'})`).join('; ')}</div>)}
            </>
          )}
        </div>
      )}

      {tab === 'poderes' && (
        <div>
          {d.presidency?.competence && (
            <div className="card mb"><h4>Competências da Presidência (SIORG)</h4><div className="exe-competence">{d.presidency.competence}</div></div>
          )}
          {Object.entries(powers).map(([group, items]) => (
            <div key={group} className="mb">
              <h3>{group}</h3>
              <div className="exe-powers">
                {items.map((p) => (
                  <div key={p.id} className="card exe-power">
                    <div className="art">CF, {p.article}</div>
                    <h4 style={{ color: 'var(--fg-0)', textTransform: 'none', letterSpacing: 0, fontSize: 13 }}>{p.title}</h4>
                    <p className="small">{p.text}</p>
                    {p.links?.length > 0 && <div className="small muted">Envolve: {p.links.map((l: string) => LINK_LABEL[l] ?? l).join(', ')}</div>}
                    <SrcList sources={p.sources} />
                  </div>
                ))}
              </div>
            </div>
          ))}
          {it.check && (
            <div className="card mb">
              <h3>Quem controla o Executivo</h3>
              <div className="exe-flow">
                {it.check.map((c: any) => (
                  <div key={c.id} style={{ display: 'contents' }}>
                    <b>{c.by}</b><span className="arrow">→</span>
                    <div><b>{c.title}</b> <span className="muted">({c.article})</span><div className="small">{c.text}</div><SrcList sources={c.sources} /></div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {it.ministers_role?.[0] && <div className="card"><h3>O papel dos ministros (CF, {it.ministers_role[0].article})</h3><p className="small">{it.ministers_role[0].text}</p><SrcList sources={it.ministers_role[0].sources} /></div>}
        </div>
      )}

      {tab === 'fontes' && (
        <div className="card">
          {d.sources.map((s) => <div key={s.id} className="row"><a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> <span className="muted small">· última coleta {fmtDateTime(s.last_success_at)}</span></div>)}
          <p className="small muted">{guide.data?.items?.disclaimer?.[0]?.text ?? 'A estrutura e as competências vêm do SIORG (oficial). Os titulares vêm da lista colaborativa da Wikipédia e são marcados como dado extraído, não verificado; cada mandato traz as referências citadas lá.'}</p>
        </div>
      )}
    </div>
  )
}
