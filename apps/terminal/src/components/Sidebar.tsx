import { Button, Icon, type IconName } from '@blueprintjs/core'
import { useState } from 'react'
import type { Institution } from '../api/client'
import { useStore, type View } from '../store'

const NAV: { view: View; label: string; icon: IconName }[] = [
  { view: 'inicio', label: 'Central de situação', icon: 'control' },
  { view: 'senado', label: 'Senado Federal', icon: 'layout-circle' },
  { view: 'stf', label: 'STF e caso Master', icon: 'take-action' },
  { view: 'noticias', label: 'Notícias', icon: 'feed' },
  { view: 'sources', label: 'Fontes e cobertura', icon: 'database' },
]

export function Sidebar({ inst, onTerminal }: { inst?: Institution; onTerminal: () => void }) {
  const { view, setView, sidebarCollapsed, toggleSidebar } = useStore()
  const [closedFolders, setClosedFolders] = useState<string[]>([])
  const navItem = (n: typeof NAV[number], nested = false) => (
    <button key={n.view} className={`nav-item ${nested ? 'nested' : ''} ${view === n.view ? 'active' : ''}`} onClick={() => setView(n.view)}
      title={n.label} aria-label={n.label} aria-current={view === n.view ? 'page' : undefined}>
      <Icon icon={n.icon} size={14} /><span className="nav-label">{n.label}</span>
    </button>
  )
  return (
    <nav className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`} aria-label="Navegação">
      <div className="sidebar-head">
        {inst && !sidebarCollapsed && (
          <div className="inst-identity">
            <img className="sidebar-art" src="/escola-de-atenas.webp" alt="Escola de Atenas, de Rafael" />
            <div className="name">Seu observatório político</div>
            <div className="meta">Brasil · monitor institucional</div>
          </div>
        )}
        <Button minimal small icon={sidebarCollapsed ? 'menu-open' : 'menu-closed'} onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
          title={sidebarCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'} />
      </div>
      {navItem(NAV[0])}
      {[{ name: 'Instituições', views: ['senado', 'stf'] }, { name: 'Biblioteca', views: ['noticias', 'sources'] }].map((folder) => {
        const open = !closedFolders.includes(folder.name)
        return <div className="nav-folder" key={folder.name}>
          <button className="folder-toggle" aria-expanded={open} aria-controls={`folder-${folder.name}`} onClick={() => setClosedFolders((closed) => open ? [...closed, folder.name] : closed.filter((name) => name !== folder.name))}>
            <Icon icon={open ? 'folder-open' : 'folder-close'} size={13} /><span>{folder.name}</span><Icon icon={open ? 'chevron-down' : 'chevron-right'} size={10} />
          </button>
          <div id={`folder-${folder.name}`} className={`folder-items ${open ? '' : 'is-collapsed'}`}>{NAV.filter((n) => folder.views.includes(n.view)).map((n) => navItem(n, true))}</div>
        </div>
      })}
      <div className="sidebar-bottom">
        <button className="nav-item" onClick={onTerminal} title="Terminal local"><Icon icon="console" size={14} /><span className="nav-label">Terminal local</span></button>
        {!sidebarCollapsed && <><div className="nav-section">Método Politeia</div><p>Fatos com fonte.<br />Inferências com contexto.</p></>}
        <span className="system-signature"><span className="dot ok" />{!sidebarCollapsed && 'Inteligência rastreável'}</span>
      </div>
    </nav>
  )
}
