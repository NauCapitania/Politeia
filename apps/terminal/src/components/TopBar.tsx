import { Icon } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useStore } from '../store'
import { fmtDateTime } from '../format'

const VIEW_LABEL: Record<string, string> = {
  inicio: 'Central de situação', senado: 'Senado Federal', stf: 'STF e caso Master', noticias: 'Notícias', sources: 'Fontes e cobertura',
}

export function TopBar({ current, onCommand, onTerminal }: { current?: Institution; onCommand: () => void; onTerminal: () => void }) {
  const { view, setView } = useStore()
  return (
    <header className="topbar">
      <button className="brand" onClick={() => setView('inicio')} aria-label="Politeia, início"><img className="brand-art" src="/politeia-icon.png" alt="" title="Escola de Atenas, Rafael" />Politeia<span className="brand-os">OS</span></button>
      <div className="workspace-path"><span>Observatório</span><Icon icon="chevron-right" size={10} /><b>{VIEW_LABEL[view]}</b></div>
      <div className="spacer" />
      <button className="command-trigger" aria-label="Buscar ou navegar" onClick={onCommand}><Icon icon="search" size={14} /><span>Buscar ou navegar</span><kbd>Ctrl K</kbd></button>
      <button className="terminal-trigger" onClick={onTerminal} aria-label="Abrir terminal local" title="Terminal local"><Icon icon="console" size={16} /></button>
      {current && (
        <span className="freshness" title="Última coleta concluída; não é uma transmissão ao vivo">
          <span className={`dot ${current.last_ingested_at ? 'ok' : 'warn'}`} />
          {current.last_ingested_at ? `Coleta ${fmtDateTime(current.last_ingested_at)}` : 'Sem coleta registrada'}
        </span>
      )}
    </header>
  )
}
