import { useState } from 'react'
import { useCommittee } from '../api/client'
import { useCamaraCommittee, type CamaraCommitteeMember } from '../api/camara'

// Ontology holdings intentionally contain only committee leaders. Load the complete
// current roster on demand from the existing API (also exported in static snapshots).
export function CommitteeMembers({ id, camara }: { id: string; camara: boolean }) {
  const senate = useCommittee(camara ? null : id)
  const chamber = useCamaraCommittee(camara ? id : null)
  const query = camara ? chamber : senate
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const members: CamaraCommitteeMember[] = query.data?.members ?? []
  const filtered = members.filter((m) => m.name.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR')))
  return <details className="atlas-section" open>
    <summary>Composição da comissão <span>{members.length}</span></summary>
    <p>Titulares e suplentes registrados na composição atual.</p>
    {query.isLoading && <p role="status">Carregando composição…</p>}
    {query.isError && <p role="alert">Não foi possível carregar a composição. <button onClick={() => query.refetch()}>Tentar novamente</button></p>}
    {query.isSuccess && <>
      <input className="atlas-person-search" aria-label="Buscar ocupante" placeholder="Buscar pessoa…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0) }} />
      {!filtered.length && <p>Nenhum integrante encontrado nesta consulta. Isso não significa cargo vago.</p>}
      {filtered.slice(page * 12, (page + 1) * 12).map((m, i) => <article className="atlas-person" key={`${m.person_id}-${m.seat_kind}-${i}`}>
        <strong>{m.name}</strong>
        <p>{[m.role?.toLocaleLowerCase('pt-BR'), m.seat_kind, m.party, m.uf].filter(Boolean).join(' · ')}</p>
      </article>)}
      {filtered.length > 12 && <div className="atlas-pager"><button disabled={!page} onClick={() => setPage(page - 1)}>Anterior</button><span>{page * 12 + 1}–{Math.min((page + 1) * 12, filtered.length)}</span><button disabled={(page + 1) * 12 >= filtered.length} onClick={() => setPage(page + 1)}>Próxima</button></div>}
    </>}
  </details>
}
