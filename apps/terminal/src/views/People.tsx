import { HTMLSelect, NonIdealState } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useComposition, useMembers } from '../api/client'
import { useStore } from '../store'
import { PARTICIPATION_LABEL, fmtDate, partyColor } from '../format'

export function People({ inst }: { inst: Institution }) {
  const { search, partyFilter, setPartyFilter, select, selectedId } = useStore()
  const comp = useComposition(inst.id)
  const members = useMembers(inst.id, { q: search || undefined, party: partyFilter ?? undefined })
  return (
    <div className="view">
      <div className="view-header">
        <h1>{inst.terminology.members}</h1>
        <span className="sub">{members.data?.total ?? '—'} de {inst.observed_member_count} em exercício</span>
      </div>
      <div className="toolbar">
        <HTMLSelect aria-label="Filtrar partido" value={partyFilter ?? ''} onChange={(e) => setPartyFilter(e.currentTarget.value || null)}
          options={[{ value: '', label: 'Todos os partidos' }, ...(comp.data?.groups.filter((g) => g.party).map((g) => ({ value: g.party!.id, label: `${g.party!.abbreviation} (${g.count})` })) ?? [])]} />
      </div>
      {members.data?.total === 0 ? <NonIdealState icon="search" title="Nenhum membro encontrado" /> : (
        <section className="panel">
          <table className="table">
            <thead><tr><th></th><th>Nome</th><th>Partido</th><th>{inst.terminology.represented_unit}</th><th>Participação</th><th>Mandato</th><th>Proposições</th></tr></thead>
            <tbody>
              {members.data?.items.map((m) => (
                <tr key={m.mandate_id} className={`row ${selectedId === m.person_id ? 'selected' : ''}`} onClick={() => select(m.person_id)}>
                  <td style={{ width: 36 }}>{m.photo_url ? <img src={m.photo_url} alt="" width={24} height={30} style={{ objectFit: 'cover', borderRadius: 2 }} /> : <span className="faint">—</span>}</td>
                  <td>{m.name}{m.full_name && <div className="faint" style={{ fontSize: 11 }}>{m.full_name}</div>}</td>
                  <td>{m.party ? <span className="chip"><span className="swatch" style={{ background: partyColor(m.party.abbreviation) }} />{m.party.abbreviation}</span> : <span className="faint">—</span>}</td>
                  <td className="mono">{m.represented_unit ?? '—'}</td>
                  <td>{m.participation ? PARTICIPATION_LABEL[m.participation] : <span className="faint">não informado</span>}</td>
                  <td className="mono">{m.start_date ? `${fmtDate(m.start_date)} – ${fmtDate(m.end_date)}` : <span className="faint">datas não publicadas</span>}</td>
                  <td className="mono">{m.authored_proposals}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
