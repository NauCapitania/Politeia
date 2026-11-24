import { InputGroup } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useStore } from '../store'
import { fmtDateTime } from '../format'

const VIEW_LABEL: Record<string, string> = {
  senado: 'Senado', votacoes: 'Votações', presidencia2025: 'Presidência 2025', presidencia2027: 'Presidência 2027',
  stf: 'STF e caso Master', noticias: 'Notícias', proposals: 'Proposições', sources: 'Fontes e cobertura',
}

export function TopBar({ current }: { current?: Institution }) {
  const { search, setSearch, setView, view } = useStore()
  return (
    <header className="topbar">
      <div className="brand"><span className="brand-mark" />Politeia</div>
      <span className="muted">Monitor do Senado Federal</span>
      <InputGroup
        leftIcon="search"
        placeholder="Buscar proposições…"
        value={search}
        onValueChange={(v) => {
          setSearch(v)
          if (v && view !== 'proposals') setView('proposals')
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
