import { Icon } from '@blueprintjs/core'
import { isStatic, useSnapshotMeta, type Institution } from '../api/client'
import { useStore } from '../store'
import { fmtDateTime } from '../format'

const VIEW_LABEL: Record<string, string> = {
  inicio: 'Central de situação', senado: 'Senado Federal', stf: 'STF e caso Master', noticias: 'Notícias', sources: 'Fontes e cobertura',
}
const snapshotTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo',
})

export function TopBar({ current, onCommand, onTerminal, theme, onTheme }: { current?: Institution; onCommand: () => void; onTerminal: () => void; theme: 'dark' | 'light'; onTheme: () => void }) {
  const { view, setView } = useStore()
  const { data: snapshot, isError } = useSnapshotMeta()
  return (
    <header className="topbar">
      <button className="brand" onClick={() => setView('inicio')} aria-label="Politeia, início"><img className="brand-art" src="/politeia-icon.png" alt="" title="Escola de Atenas, Rafael" />Politeia<span className="brand-os">OS</span></button>
      <div className="workspace-path"><span>Observatório</span><Icon icon="chevron-right" size={10} /><b>{VIEW_LABEL[view]}</b></div>
      <div className="spacer" />
      <button className="command-trigger" aria-label="Buscar ou navegar" onClick={onCommand}><Icon icon="search" size={14} /><span>Buscar ou navegar</span><kbd>Ctrl K</kbd></button>
      <button className="terminal-trigger" onClick={onTerminal} aria-label="Abrir terminal local" title="Terminal local"><Icon icon="console" size={16} /></button>
      <button className="terminal-trigger theme-trigger" onClick={onTheme} aria-label={`Alternar para modo ${theme === 'dark' ? 'claro' : 'escuro'}`} title={`Modo ${theme === 'dark' ? 'claro' : 'escuro'}`}><Icon icon={theme === 'dark' ? 'lightbulb' : 'moon'} size={15} /></button>
      {isStatic() ? (
        snapshot ? <span className="freshness">
          <span className="dot ok" />
          <time dateTime={snapshot.generated_at}>Último snapshot: {snapshotTime.format(new Date(snapshot.generated_at))} BRT</time>
        </span> : isError && <span className="freshness">Data do snapshot indisponível</span>
      ) : current && (
        <span className="freshness" title="Última coleta concluída; não é uma transmissão ao vivo">
          <span className={`dot ${current.last_ingested_at ? 'ok' : 'warn'}`} />
          {current.last_ingested_at ? `Coleta ${fmtDateTime(current.last_ingested_at)}` : 'Sem coleta registrada'}
        </span>
      )}
    </header>
  )
}
