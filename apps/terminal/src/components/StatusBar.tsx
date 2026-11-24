import { useEffect, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'
import { Icon } from '@blueprintjs/core'
import { useStore } from '../store'
import { isStatic, useSnapshotMeta } from '../api/client'

const snapshotTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo',
})

export function StatusBar({ onCommand }: { onCommand: () => void }) {
  const [now, setNow] = useState(() => new Date())
  const fetching = useIsFetching()
  const snapshot = useSnapshotMeta()
  const setView = useStore((s) => s.setView)
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30_000); return () => window.clearInterval(timer) }, [])
  return <footer className={`statusbar ${isStatic() ? 'snapshot-status' : ''}`}><span className="status-activity"><span className={`dot ${fetching ? 'warn' : 'ok'}`} />{fetching ? 'Consultando a base…' : 'Espaço de trabalho pronto'}</span>
    {isStatic() && <span className="mobile-freshness">{snapshot.data ? <time dateTime={snapshot.data.generated_at}>Base · {snapshotTime.format(new Date(snapshot.data.generated_at))} BRT</time> : snapshot.isError ? 'Data da base indisponível' : 'Consultando a base…'}</span>}
    <button onClick={() => setView('sources')}><Icon icon="database" size={11} /> Fontes e cobertura</button><span className="spacer" />
    <button onClick={onCommand} className="status-command">Central de comandos <kbd>Ctrl K</kbd></button><time dateTime={now.toISOString()}>{new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit' }).format(now)} Brasília</time>
  </footer>
}
