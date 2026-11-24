import { useMemo, useState } from 'react'
import { InputGroup, NonIdealState, Spinner } from '@blueprintjs/core'
import { useCommittee, useCommittees } from '../api/client'
import { fmtDate, partyColor } from '../format'
import { useStore } from '../store'

const ROLE: Record<string, string> = { PRESIDENTE: 'Presidente', 'VICE-PRESIDENTE': 'Vice-presidente', RELATOR: 'Relator' }

export function Comissoes() {
  const list = useCommittees()
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState<string | null>(null)
  const rows = useMemo(() => (list.data ?? []).filter((c) =>
    !q || `${c.abbreviation} ${c.name}`.toLowerCase().includes(q.toLowerCase())), [list.data, q])
  const current = focus ?? list.data?.find((c) => c.abbreviation === 'CCJ')?.id ?? list.data?.[0]?.id
  const groups = useMemo(() => {
    const m = new Map<string, any[]>()
    rows.forEach((c) => m.set(c.type ?? 'Outras', [...(m.get(c.type ?? 'Outras') ?? []), c]))
    return [...m.entries()]
  }, [rows])
  return (
    <div className="view">
      <h1>Comissões do Senado</h1>
      <p className="lede">Comissões permanentes, temporárias e CPIs em atividade, com a composição atual publicada nos Dados Abertos do Senado. Clique em um senador para abrir o perfil.</p>
      {list.isLoading && <Spinner size={24} />}
      {list.data && !list.data.length && <NonIdealState icon="people" title="Comissões ainda não ingeridas" description="Execute `python -m engine.cli sync --scope committees`." />}
      {!!list.data?.length && (
        <div className="committees">
          <div className="committee-list">
            <InputGroup small leftIcon="search" placeholder="Filtrar comissões…" value={q} onValueChange={setQ} />
            {groups.map(([type, cs]) => (
              <div key={type}>
                <div className="nav-section">{type}</div>
                {cs.map((c) => (
                  <button key={c.id} className={`list-row ${c.id === current ? 'active' : ''}`} onClick={() => setFocus(c.id)}>
                    <b className="mono">{c.abbreviation}</b>
                    <span className="grow">{c.name}</span>
                    <span className="faint mono">{c.titulares}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>
          {current && <CommitteeDetail id={current} />}
        </div>
      )}
    </div>
  )
}

function CommitteeDetail({ id }: { id: string }) {
  const { data, isLoading } = useCommittee(id)
  const select = useStore((s) => s.select)
  if (isLoading || !data) return <Spinner size={24} />
  const a = data.attributes ?? {}
  const by = (k: string) => data.members.filter((m: any) => m.seat_kind === k)
  const leaders = data.members.filter((m: any) => m.role)
  return (
    <div className="card committee-detail">
      <h2>{data.abbreviation} — {data.name}</h2>
      {a.subtitle && <p className="muted">{a.subtitle}</p>}
      {a.purpose && <p>{a.purpose}</p>}
      <div className="facts">
        {leaders.map((m: any) => (
          <span key={m.person_id}><span className="faint">{ROLE[m.role] ?? m.role}</span> <a className="link" onClick={() => select(m.person_id)}>{m.name}</a> ({m.party}-{m.uf})</span>
        ))}
        {a.meetings && <span><span className="faint">Reuniões</span> {a.meetings}</span>}
        {a.url && <a className="link" href={a.url} target="_blank" rel="noreferrer">Página oficial ↗</a>}
      </div>
      {(['titular', 'suplente'] as const).map((k) => (
        <div key={k}>
          <h3>{k === 'titular' ? 'Titulares' : 'Suplentes'} ({by(k).length}{a.seats?.[k === 'titular' ? 'titulares' : 'suplentes'] ? ` de ${a.seats[k === 'titular' ? 'titulares' : 'suplentes']}` : ''})</h3>
          <div className="member-grid">
            {by(k).map((m: any) => (
              <button key={m.person_id} className="member-chip" onClick={() => select(m.person_id)} title={m.bloc ?? undefined}>
                <i style={{ background: partyColor(m.party) }} />
                <span className="grow">{m.name}</span>
                <span className="faint mono">{m.party}-{m.uf}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
      <p className="faint" style={{ marginTop: 12 }}>Composição observada em {fmtDate(data.last_observed_at)} · Dados Abertos do Senado</p>
    </div>
  )
}
