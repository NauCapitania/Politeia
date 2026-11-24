import { Button, Icon, type IconName } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useStore, type View } from '../store'

const NAV: { view: View; label: string; icon: IconName }[] = [
  { view: 'inicio', label: 'Central de situação', icon: 'control' },
  { view: 'senado', label: 'Senado Federal', icon: 'layout-circle' },
  { view: 'stf', label: 'STF e caso Master', icon: 'take-action' },
  { view: 'noticias', label: 'Notícias', icon: 'feed' },
  { view: 'sources', label: 'Fontes e cobertura', icon: 'database' },
]

export function Sidebar({ inst }: { inst?: Institution }) {
  const { view, setView, sidebarCollapsed, toggleSidebar } = useStore()
  return (
    <nav className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`} aria-label="Navegação">
      <div className="sidebar-head">
        {inst && !sidebarCollapsed && (
          <div className="inst-identity">
            <div className="name">Seu observatório político</div>
            <div className="meta">Brasil · monitor institucional</div>
          </div>
        )}
        <Button minimal small icon={sidebarCollapsed ? 'menu-open' : 'menu-closed'} onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
          title={sidebarCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'} />
      </div>
      {!sidebarCollapsed && <div className="nav-section">Espaços de trabalho</div>}
      {NAV.map((n) => (
        <button key={n.view} className={`nav-item ${view === n.view ? 'active' : ''}`} onClick={() => setView(n.view)}
          title={sidebarCollapsed ? n.label : undefined} aria-label={n.label} aria-current={view === n.view ? 'page' : undefined}>
          <Icon icon={n.icon} size={14} />
          {!sidebarCollapsed && <span>{n.label}</span>}
        </button>
      ))}
      <div className="sidebar-bottom">
        {!sidebarCollapsed && <><div className="nav-section">Método Politeia</div><p>Fatos com fonte.<br />Inferências com contexto.</p></>}
        <span className="system-signature"><span className="dot ok" />{!sidebarCollapsed && 'Inteligência rastreável'}</span>
      </div>
    </nav>
  )
}
