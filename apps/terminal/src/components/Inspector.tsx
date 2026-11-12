import { Button, Spinner } from '@blueprintjs/core'
import { motion } from 'motion/react'
import type { Institution, Relationship } from '../api/client'
import { useEntity, useRelationships, useTimeline } from '../api/client'
import { useStore } from '../store'
import { EPISTEMIC_LABEL, fmtDate, partyColor } from '../format'
import { SourceLink } from './SourceLink'

const KIND_LABEL: Record<string, string> = { person: 'Pessoa', party: 'Partido', mandate: 'Mandato', proposal: 'Proposição', institution: 'Instituição' }

export function Inspector({ inst }: { inst?: Institution }) {
  const { selectedId, select, setView } = useStore()
  const entity = useEntity(selectedId)
  const rels = useRelationships(selectedId)
  const timeline = useTimeline(selectedId)

  if (!selectedId) {
    return (
      <aside className="inspector" aria-label="Inspetor">
        <div className="inspector-empty">
          <div className="insp-kind">Inspetor</div>
          <p>Selecione um assento, pessoa, partido ou proposição para ver atributos, relações, linha do tempo e a fonte oficial de cada informação.</p>
          {inst && (
            <dl className="kv">
              <dt>Fonte</dt><dd>{inst.sources[0]?.name}</dd>
              <dt>Pacote</dt><dd className="mono">{inst.pack_id}@{inst.pack_version}</dd>
              <dt>Site oficial</dt><dd><a className="link" href={inst.website} target="_blank" rel="noreferrer">{inst.website}</a></dd>
            </dl>
          )}
        </div>
      </aside>
    )
  }
  const e = entity.data
  const a = (e?.attributes ?? {}) as Record<string, any>
  const mandate = rels.data?.find((r) => r.kind === 'holds_mandate')
  const currentParty = rels.data?.find((r) => r.kind === 'current_party')
  const history = rels.data?.filter((r) => r.kind === 'party_affiliation') ?? []
  const authored = rels.data?.filter((r) => r.kind === 'authored') ?? []

  return (
    <aside className="inspector" aria-label="Inspetor">
      {entity.isLoading && <div style={{ padding: 24 }}><Spinner size={18} /></div>}
      {e && (
        <motion.div key={e.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.16 }}>
          <div className="insp-head">
            {e.kind === 'person' && a.photo_url && <img src={a.photo_url} alt="" referrerPolicy="no-referrer" />}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="insp-kind">{KIND_LABEL[e.kind]}</div>
              <div className="insp-title">{e.label}</div>
              {e.kind === 'person' && a.full_name && <div className="muted">{a.full_name}</div>}
              {currentParty && (
                <span className="chip" style={{ marginTop: 6, cursor: 'pointer' }} onClick={() => select(currentParty.target)}>
                  <span className="swatch" style={{ background: partyColor(currentParty.label) }} />{currentParty.label}
                </span>
              )}
            </div>
            <Button variant="minimal" icon="cross" aria-label="Fechar" onClick={() => select(null)} />
          </div>

          {e.kind === 'person' && (
            <div className="insp-section">
              <h3>Mandato</h3>
              {mandate ? (
                <dl className="kv">
                  <dt>Cargo</dt><dd>{mandate.label}</dd>
                  <dt>Situação</dt><dd>{mandate.is_current ? 'Em exercício' : 'Não listado atualmente'}</dd>
                  <dt>Início</dt><dd>{mandate.valid_from ? fmtDate(mandate.valid_from) : <span className="faint">não publicado pela fonte</span>}</dd>
                  <dt>Fim</dt><dd>{mandate.valid_to ? fmtDate(mandate.valid_to) : <span className="faint">não publicado pela fonte</span>}</dd>
                  <dt>Status</dt><dd><Epistemic s={mandate.epistemic_status} /></dd>
                </dl>
              ) : <span className="faint">Sem mandato registrado</span>}
              {a.profile_url && <a className="link" style={{ display: 'block', marginTop: 10 }} href={a.profile_url} target="_blank" rel="noreferrer">Página oficial ↗</a>}
            </div>
          )}

          {e.kind === 'proposal' && <ProposalDetail a={a} />}
          {e.kind === 'party' && (
            <div className="insp-section">
              <h3>Partido</h3>
              <dl className="kv"><dt>Nome</dt><dd>{a.name ?? <span className="faint">não informado pela fonte</span>}</dd></dl>
              <p className="faint" style={{ marginTop: 8 }}>{a.scope_note}</p>
              <Button size="small" icon="graph" onClick={() => setView('graph')}>Ver no grafo</Button>
            </div>
          )}

          {e.kind === 'party' && rels.data && (
            <div className="insp-section">
              <h3>Membros atuais · {rels.data.length}</h3>
              {rels.data.map((r) => (
                <div key={r.id}><a className="link" onClick={() => select(r.source)} style={{ cursor: 'pointer' }}>{r.label}</a></div>
              ))}
            </div>
          )}

          {history.length > 0 && (
            <div className="insp-section">
              <h3>Histórico partidário</h3>
              <ul className="timeline">
                {history.sort((x, y) => String(y.valid_from).localeCompare(String(x.valid_from))).map((r) => (
                  <li key={r.id}>
                    <span className="mono faint">{fmtDate(r.valid_from)}</span>
                    <span><span className="swatch" style={{ background: partyColor(r.label), marginRight: 6 }} />{r.label}
                      <span className="faint"> {r.valid_to ? `até ${fmtDate(r.valid_to)}` : '· atual'}</span></span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {authored.length > 0 && (
            <div className="insp-section">
              <h3>Proposições de autoria · {authored.length}</h3>
              {authored.slice(0, 12).map((r) => <RelLink key={r.id} r={r} onClick={() => select(r.target)} />)}
            </div>
          )}

          {timeline.data && timeline.data.length > 0 && e.kind !== 'proposal' && (
            <div className="insp-section">
              <h3>Linha do tempo</h3>
              <ul className="timeline">
                {timeline.data.slice(0, 15).map((t, i) => (
                  <li key={i}><span className="mono faint">{fmtDate(String(t.date))}</span><span>{t.label}</span></li>
                ))}
              </ul>
            </div>
          )}

          <div className="insp-section">
            <h3>Identificadores</h3>
            {e.identifiers.length ? (
              <div>
                {e.identifiers.map((i) => (
                  <div key={`${i.scheme}:${i.value}`} style={{ marginBottom: 6 }}>
                    <div className="mono faint">{i.scheme}</div>
                    <div className="mono">{i.value} {i.quality !== 'official' && <span className="status extracted">{i.quality}</span>}</div>
                  </div>
                ))}
              </div>
            ) : <span className="faint">Nenhum identificador externo</span>}
            <div className="faint mono" style={{ marginTop: 8 }}>politeia: {e.id}</div>
          </div>

          <div className="insp-section">
            <h3>Fontes</h3>
            {e.sources.length ? e.sources.map((s) => <SourceLink key={`${s.raw_record_id}${s.json_path}`} source={s} />)
              : <span className="faint">Derivado; ver relações</span>}
          </div>
        </motion.div>
      )}
    </aside>
  )
}

function Epistemic({ s }: { s: string }) {
  return <span className={`status ${s}`}>{EPISTEMIC_LABEL[s] ?? s}</span>
}

function RelLink({ r, onClick }: { r: Relationship; onClick: () => void }) {
  return (
    <div style={{ display: 'flex', gap: 8, padding: '3px 0' }}>
      <span className="mono faint" style={{ width: 76 }}>{fmtDate(r.valid_from)}</span>
      <a className="link" style={{ cursor: 'pointer' }} onClick={onClick}>{r.label}</a>
    </div>
  )
}

function ProposalDetail({ a }: { a: Record<string, any> }) {
  const { select } = useStore()
  const events = (a.events ?? []) as { id: string; event_date: string; description: string; body: string }[]
  return (
    <>
      <div className="insp-section">
        <h3>Ementa</h3>
        <p style={{ margin: 0, lineHeight: 1.5 }}>{a.ementa ?? <span className="faint">sem ementa</span>}</p>
      </div>
      <div className="insp-section">
        <h3>Dados</h3>
        <dl className="kv">
          <dt>Tipo</dt><dd>{a.type_name}</dd>
          <dt>{a.date_semantics === 'publication' ? 'Publicação' : 'Apresentação'}</dt><dd>{fmtDate(a.introduced_on)}</dd>
          <dt>Situação</dt><dd>{a.status ?? <span className="faint">não publicada pela fonte</span>}</dd>
          {a.status_date && <><dt>Desde</dt><dd>{fmtDate(a.status_date)}</dd></>}
          {a.in_progress != null && <><dt>Tramitando</dt><dd>{a.in_progress ? 'Sim' : 'Não'}</dd></>}
        </dl>
        {a.official_url && <a className="link" style={{ display: 'block', marginTop: 10 }} href={a.official_url} target="_blank" rel="noreferrer">Registro oficial ↗</a>}
        {a.source_attributes?.document_url && <a className="link" style={{ display: 'block', marginTop: 4 }} href={a.source_attributes.document_url} target="_blank" rel="noreferrer">Documento ↗</a>}
      </div>
      <div className="insp-section">
        <h3>Autoria</h3>
        {(a.authors ?? []).map((au: any) => (
          <div key={au.ordinal} style={{ marginBottom: 6 }}>
            {au.person_id ? <a className="link" style={{ cursor: 'pointer' }} onClick={() => select(au.person_id)}>{au.name}</a> : <span>{au.name}</span>}
            <span className="faint"> · {au.kind}</span> <span className={`status ${au.epistemic_status}`}>{au.resolution}</span>
            {au.note && <div className="faint" style={{ fontSize: 11 }}>{au.note}</div>}
          </div>
        ))}
      </div>
      <div className="insp-section">
        <h3>Tramitação registrada · {events.length}</h3>
        {events.length === 0 ? <span className="faint">A fonte não publica histórico de tramitação para esta proposição.</span> : (
          <ul className="timeline">
            {events.slice(0, 20).map((ev) => (
              <li key={ev.id}><span className="mono faint">{fmtDate(ev.event_date)}</span>
                <span>{ev.body && <span className="chip mono" style={{ marginRight: 6 }}>{ev.body}</span>}{ev.description}</span></li>
            ))}
          </ul>
        )}
      </div>
    </>
  )
}
