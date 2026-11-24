import { useEffect, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'
import { Icon } from '@blueprintjs/core'
import { useStore } from '../store'

export function StatusBar({ onCommand }: { onCommand: () => void }) {
  const [now, setNow] = useState(() => new Date())
  const fetching = useIsFetching()
  const setView = useStore((s) => s.setView)
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30_000); return () => window.clearInterval(timer) }, [])
  return <footer className="statusbar"><span className="status-activity"><span className={`dot ${fetching ? 'warn' : 'ok'}`} />{fetching ? 'Consultando a base…' : 'Espaço de trabalho pronto'}</span>
    <button onClick={() => setView('sources')}><Icon icon="database" size={11} /> Fontes e cobertura</button><span className="spacer" />
    <button onClick={onCommand} className="status-command">Central de comandos <kbd>Ctrl K</kbd></button><time dateTime={now.toISOString()}>{new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit' }).format(now)} Brasília</time>
  </footer>
}
