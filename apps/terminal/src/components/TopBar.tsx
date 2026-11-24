import { InputGroup } from '@blueprintjs/core'
import { isStatic, useSnapshotMeta, type Institution } from '../api/client'
import { useStore } from '../store'
import { fmtDateTime } from '../format'

const VIEW_LABEL: Record<string, string> = {
  senado: 'Senado Federal', stf: 'STF e caso Master', noticias: 'Notícias', sources: 'Fontes e cobertura',
}
const snapshotTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo',
})

export function TopBar({ current }: { current?: Institution }) {
  const { search, setSearch, setSenadoTab, view, senadoTab } = useStore()
  const { data: snapshot, isError } = useSnapshotMeta()
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
          if (v && !(view === 'senado' && senadoTab === 'proposicoes')) setSenadoTab('proposicoes')
        }}
        style={{ width: 320 }}
        small
      />
      <span className="muted">{VIEW_LABEL[view]}</span>
      <div className="spacer" />
      {isStatic() ? (
        snapshot ? <span className="freshness">
          <span className="dot ok" />
          <time dateTime={snapshot.generated_at}>Último snapshot: {snapshotTime.format(new Date(snapshot.generated_at))} BRT</time>
        </span> : isError && <span className="freshness">Data do snapshot indisponível</span>
      ) : current && (
        <span className="freshness" title="Última ingestão concluída">
          <span className={`dot ${current.last_ingested_at ? 'ok' : 'warn'}`} />
          {current.last_ingested_at ? `sincronizado ${fmtDateTime(current.last_ingested_at)}` : 'nunca sincronizado'}
        </span>
      )}
    </header>
  )
}
