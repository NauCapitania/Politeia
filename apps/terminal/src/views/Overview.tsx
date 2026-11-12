import type { Institution } from '../api/client'
import { useCapabilities, useComposition } from '../api/client'
import { useStore } from '../store'
import { CAPABILITY_LABEL, STATUS_LABEL, partyColor } from '../format'
import { Hemicycle } from './Hemicycle'

export function Overview({ inst }: { inst: Institution }) {
  const comp = useComposition(inst.id)
  const caps = useCapabilities(inst.id)
  const { partyFilter, setPartyFilter, select } = useStore()
  const max = Math.max(1, ...(comp.data?.groups.map((g) => g.count) ?? [1]))
  return (
    <div className="view">
      <div className="view-header">
        <h1>{inst.official_name}</h1>
        <span className="sub">{inst.terminology.members} · {inst.geographic_scope}</span>
      </div>
      {comp.data?.discrepancy && <div className={`notice ${comp.data.seat_count ? '' : 'info'}`}>{comp.data.discrepancy}</div>}
      <div className="grid-2">
        <section className="panel">
          <div className="panel-head">Composição atual</div>
          <div style={{ padding: 16 }}>
            {comp.isLoading ? <div className="skeleton" style={{ height: 320 }} /> : comp.data && <Hemicycle comp={comp.data} />}
          </div>
          {inst.seat_count_source && <div className="faint" style={{ padding: '0 16px 12px', fontSize: 11 }}>Assentos: {inst.seat_count_source}</div>}
        </section>
        <section className="panel">
          <div className="panel-head">Partidos · {comp.data?.groups.length ?? '—'}</div>
          <div className="legend">
            {comp.data?.groups.map((g) => {
              const id = g.party?.id ?? null
              return (
                <div key={id ?? 'none'} className={`legend-row ${partyFilter && partyFilter === id ? 'active' : ''}`}
                  onClick={() => setPartyFilter(partyFilter === id ? null : id)}
                  onDoubleClick={() => id && select(id)} role="button" aria-pressed={partyFilter === id}>
                  <span className="swatch" style={{ background: partyColor(g.party?.abbreviation) }} />
                  <span style={{ width: 96 }}>{g.party?.abbreviation ?? 'Sem partido'}</span>
                  <span className="bar"><i style={{ width: `${(g.count / max) * 100}%`, background: partyColor(g.party?.abbreviation) }} /></span>
                  <span className="mono" style={{ width: 24, textAlign: 'right' }}>{g.count}</span>
                </div>
              )
            })}
          </div>
        </section>
      </div>
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">Capacidades institucionais (derivadas da ingestão)</div>
        <table className="table">
          <thead><tr><th>Capacidade</th><th>Status</th><th>Registros</th><th>Observação</th></tr></thead>
          <tbody>
            {caps.data?.map((c) => (
              <tr key={c.capability}>
                <td>{CAPABILITY_LABEL[c.capability] ?? c.capability}</td>
                <td><span className={`status ${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span></td>
                <td className="mono">{c.record_count ?? '—'}</td>
                <td className="muted">{c.note ?? coverageText(c.coverage)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

function coverageText(c: Record<string, unknown>): string {
  if ('member_authors_unresolved' in c) return `${c.member_authors_unresolved} autores parlamentares não vinculados`
  if ('introduced_from' in c) return `${c.introduced_from ?? '?'} → ${c.introduced_to ?? '?'}`
  if ('persons_covered' in c) return `${c.persons_covered} pessoas com histórico`
  return ''
}
