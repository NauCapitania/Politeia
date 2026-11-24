import { Icon, type IconName } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useCapabilities } from '../api/client'
import { useStore, type View } from '../store'

const NAV: { view: View; label: string; icon: IconName; cap?: string }[] = [
  { view: 'senado', label: 'Senado', icon: 'layout-circle', cap: 'members' },
  { view: 'votacoes', label: 'Votações', icon: 'th-list', cap: 'votes' },
  { view: 'presidencia2025', label: 'Presidência 2025', icon: 'crown' },
  { view: 'presidencia2027', label: 'Presidência 2027', icon: 'flag' },
  { view: 'stf', label: 'STF e caso Master', icon: 'take-action' },
  { view: 'noticias', label: 'Notícias', icon: 'feed', cap: 'news' },
  { view: 'proposals', label: 'Proposições', icon: 'document', cap: 'proposals' },
  { view: 'sources', label: 'Fontes e cobertura', icon: 'database' },
]

export function Sidebar({ inst }: { inst?: Institution }) {
  const { view, setView } = useStore()
  const caps = useCapabilities(inst?.id).data
  return (
    <nav className="sidebar" aria-label="Navegação">
      {inst && (
        <div className="inst-identity">
          <div className="name">{inst.official_name}</div>
          <div className="meta">{inst.jurisdiction}</div>
        </div>
      )}
      {NAV.map((n) => {
        const cap = caps?.find((c) => c.capability === n.cap)
        return (
          <button key={n.view} className={`nav-item ${view === n.view ? 'active' : ''}`} onClick={() => setView(n.view)}>
            <Icon icon={n.icon} size={14} />
            {n.label}
            {cap?.record_count != null && <span className="count">{cap.record_count}</span>}
          </button>
        )
      })}
      <div className="nav-section">Capacidades</div>
      {caps?.map((c) => (
        <div key={c.capability} className="nav-item" style={{ cursor: 'default' }} title={c.note ?? c.status}>
          <span className={`dot ${c.status === 'available' ? 'ok' : c.status === 'partial' ? 'warn' : c.status === 'ingestion_failed' ? 'err' : ''}`} />
          <span style={{ fontSize: 12, color: c.status === 'available' || c.status === 'partial' ? 'var(--fg-1)' : 'var(--fg-3)' }}>
            {CAP[c.capability] ?? c.capability}
          </span>
        </div>
      ))}
    </nav>
  )
}

const CAP: Record<string, string> = {
  members: 'Membros', mandates: 'Mandatos', party_composition: 'Composição', party_history: 'Histórico partidário',
  proposals: 'Proposições', proposal_authors: 'Autoria', proposal_events: 'Tramitação', committees: 'Comissões', votes: 'Votações',
  composition_history: 'Histórico de cadeiras', mandate_exercises: 'Exercícios', speeches: 'Discursos', news: 'Notícias',
}
