import { useEffect, useState } from 'react'
import { Button, HTMLSelect, InputGroup, NonIdealState } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useProposalTypes, useProposals } from '../api/client'
import { useStore } from '../store'
import { fmtDate } from '../format'

export function Proposals({ inst }: { inst: Institution }) {
  const { select, selectedId, search, setSearch } = useStore()
  const [type, setType] = useState('')
  const [offset, setOffset] = useState(0)
  useEffect(() => setOffset(0), [search, inst.id])
  const types = useProposalTypes(inst.id)
  const page = useProposals(inst.id, { q: search || undefined, type_code: type || undefined, offset })
  const total = page.data?.total ?? 0
  return (
    <div className="view">
      <div className="view-header"><h1>Proposições</h1><span className="sub">{total} registros ingeridos</span></div>
      <div className="toolbar">
        <InputGroup leftIcon="search" placeholder="Ementa ou número…" value={search} onValueChange={(v) => { setSearch(v); setOffset(0) }} style={{ width: 300 }} />
        <HTMLSelect aria-label="Tipo" value={type} onChange={(e) => { setType(e.currentTarget.value); setOffset(0) }}
          options={[{ value: '', label: 'Todos os tipos' }, ...(types.data?.map((t) => ({ value: t.type_code, label: `${t.type_code} · ${t.type_name} (${t.count})` })) ?? [])]} />
        <span style={{ flex: 1 }} />
        <span className="mono faint">{total ? `${offset + 1}–${Math.min(offset + 50, total)} de ${total}` : ''}</span>
        <Button icon="chevron-left" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))} aria-label="Anterior" />
        <Button icon="chevron-right" disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)} aria-label="Próxima" />
      </div>
      {page.data && total === 0 ? <NonIdealState icon="document" title="Nenhuma proposição" description="Nenhum registro corresponde aos filtros." /> : (
        <section className="panel">
          <table className="table">
            <thead><tr><th>Identificação</th><th>Ementa</th><th>Autoria</th><th>Data</th><th>Situação</th></tr></thead>
            <tbody>
              {page.data?.items.map((p) => (
                <tr key={p.id} className={`row ${selectedId === p.id ? 'selected' : ''}`} onClick={() => select(p.id)}>
                  <td className="mono" style={{ whiteSpace: 'nowrap' }}>{p.identifier}</td>
                  <td style={{ maxWidth: 520 }}>{p.ementa}</td>
                  <td>{p.authors.slice(0, 2).map((a) => a.name).join(', ')}{p.authors.length > 2 && <span className="faint"> +{p.authors.length - 2}</span>}</td>
                  <td className="mono">{fmtDate(p.introduced_on)}</td>
                  <td>{p.status ?? <span className="faint">não publicada</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
