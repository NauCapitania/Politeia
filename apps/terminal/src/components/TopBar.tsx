import { HTMLSelect, InputGroup } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useStore } from '../store'
import { fmtDateTime } from '../format'

const VIEW_LABEL = { overview: 'Visão geral', people: 'Pessoas', proposals: 'Proposições', graph: 'Grafo institucional', sources: 'Fontes e cobertura' }

export function TopBar({ institutions, current }: { institutions: Institution[]; current?: Institution }) {
  const { setInstitution, search, setSearch, setView, view } = useStore()
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark" />Politeia</div>
      <HTMLSelect
        aria-label="Instituição"
        value={current?.id ?? ''}
        onChange={(e) => setInstitution(e.currentTarget.value)}
        options={institutions.map((i) => ({ value: i.id, label: `${i.short_name} — ${i.geographic_scope}` }))}
        minimal
      />
      <InputGroup
        leftIcon="search"
        placeholder={`Buscar em ${current?.short_name ?? ''}…`}
        value={search}
        onValueChange={(v) => {
          setSearch(v)
          if (v && view !== 'people' && view !== 'proposals') setView('people')
        }}
        style={{ width: 320 }}
        small
      />
      <span className="muted">{VIEW_LABEL[view]}</span>
      <div className="spacer" />
      {current && (
        <span className="freshness" title="Última ingestão concluída">
          <span className={`dot ${current.last_ingested_at ? 'ok' : 'warn'}`} />
          {current.last_ingested_at ? `sincronizado ${fmtDateTime(current.last_ingested_at)}` : 'nunca sincronizado'}
        </span>
      )}
    </header>
  )
}
