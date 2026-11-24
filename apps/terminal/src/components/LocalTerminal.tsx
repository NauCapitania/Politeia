import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
import { Dialog, Icon } from '@blueprintjs/core'
import type { SeatRow } from '../api/client'
import { useCurrentSeats } from '../useCurrentSeats'
import { useStore } from '../store'
import { normalize } from '../format'

type Entry = { command: string; lines: string[]; matches?: SeatRow[] }

export function LocalTerminal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [history, setHistory] = useState<string[]>([])
  return isOpen ? <TerminalSession onClose={onClose} entries={entries} setEntries={setEntries} history={history} setHistory={setHistory} /> : null
}

function TerminalSession({ onClose, entries, setEntries, history, setHistory }: {
  onClose: () => void; entries: Entry[]; setEntries: Dispatch<SetStateAction<Entry[]>>
  history: string[]; setHistory: Dispatch<SetStateAction<string[]>>
}) {
  const seats = useCurrentSeats()
  const [input, setInput] = useState('')
  const [cursor, setCursor] = useState(-1)
  const output = useRef<HTMLDivElement>(null)
  const { setView, setSenadoTab, select } = useStore()

  useEffect(() => { output.current?.scrollTo?.(0, output.current.scrollHeight) }, [entries])

  function run() {
    const command = input.trim()
    if (!command) return
    setInput('')
    setHistory((old) => [command, ...old].slice(0, 40))
    setCursor(-1)
    const normalized = normalize(command).replace(/\s+/g, ' ')
    const entry: Entry = { command, lines: [] }
    if (normalized === 'limpar') { setEntries([]); return }
    if (normalized === 'ajuda') {
      entry.lines = ['resumo — composição consultada do Senado', 'buscar NOME — localizar um senador', 'abrir inicio | analises | master | congresso | senado | camara | votacoes | stf | executivo | partidos | noticias | fontes', 'limpar — limpar a tela; ↑ e ↓ — histórico de comandos']
    } else if (normalized === 'resumo') {
      entry.lines = seats.isLoading ? ['Consultando a base… Execute resumo novamente em instantes.'] : seats.isError ? ['Não foi possível consultar a composição. Abra fontes para verificar a cobertura.'] : !seats.data ? ['Sem composição disponível.'] : [
        `Composição consultada: ${seats.data.date}`,
        `${seats.data.observed} cadeiras observadas; ${new Set(seats.data.seats.map((s) => s.party).filter(Boolean)).size} partidos identificados.`,
        'Dados coletados, não transmissão ao vivo. Consulte fontes para verificar a cobertura.',
      ]
    } else if (normalized.startsWith('abrir ')) {
      const target = normalized.slice(6)
      if (target === 'master') { useStore.getState().setAnalysis('caso-master'); onClose(); return }
      if (target === 'senado' || target === 'votacoes') { setSenadoTab(target === 'senado' ? 'composicao' : 'votacoes'); onClose(); return }
      const views = { inicio: 'inicio', analises: 'analises', congresso: 'congresso', camara: 'camara', stf: 'stf', executivo: 'executivo', partidos: 'partidos', noticias: 'noticias', fontes: 'sources' } as const
      if (Object.hasOwn(views, target)) { setView(views[target as keyof typeof views]); onClose(); return }
      entry.lines = ['Pasta não encontrada. Digite ajuda para ver os destinos disponíveis.']
    } else if (normalized.startsWith('buscar ')) {
      const term = normalized.slice(7).trim()
      entry.matches = (seats.data?.seats ?? []).filter((s) => normalize(`${s.name} ${s.full_name ?? ''} ${s.party ?? ''} ${s.uf ?? ''}`).includes(term)).slice(0, 6)
      entry.lines = seats.isLoading ? ['Consultando a base… Tente novamente em instantes.'] : seats.isError ? ['Consulta indisponível. Abra fontes para verificar a cobertura.'] : [entry.matches.length ? 'Selecione um perfil para abrir as evidências:' : 'Nenhum senador encontrado na composição consultada.']
    } else { entry.lines = ['Comando não reconhecido. Digite ajuda para ver os comandos disponíveis.'] }
    setEntries((old) => [...old, entry].slice(-40))
  }

  return <Dialog isOpen onClose={onClose} className="local-terminal" aria-label="Terminal local">
    <div className="terminal-titlebar"><Icon icon="console" size={14} /><b>Terminal local</b><span>politeia / observatório</span><button onClick={onClose} aria-label="Fechar terminal"><Icon icon="cross" size={16} /></button></div>
    <div className="terminal-output" ref={output} role="log" aria-label="Saída do terminal" aria-live="polite">
      <p className="terminal-welcome">Seu observatório, por comandos.</p>
      <p>Digite <b>ajuda</b> para começar. Comandos locais, sem IA conectada.</p>
      {entries.map((entry, i) => <div className="terminal-entry" key={i}><div className="terminal-echo"><span>politeia ~ $</span> {entry.command}</div>{entry.lines.map((line, j) => <div key={j}>{line}</div>)}{entry.matches?.map((s) => <button className="terminal-match" key={s.person_id} onClick={() => { setSenadoTab('composicao'); select(s.person_id); onClose() }}><Icon icon="person" size={12} />{s.name} · {s.party ?? 'Filiação não informada'} / {s.uf}</button>)}</div>)}
    </div>
    <form className="terminal-prompt" onSubmit={(e) => { e.preventDefault(); run() }}><label htmlFor="terminal-command">politeia ~ $</label><input id="terminal-command" autoFocus autoComplete="off" spellCheck={false} aria-label="Comando do terminal" placeholder="ajuda" value={input} onChange={(e) => { setInput(e.target.value); setCursor(-1) }} onKeyDown={(e) => {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
      e.preventDefault()
      const next = e.key === 'ArrowUp' ? Math.min(cursor + 1, history.length - 1) : Math.max(cursor - 1, -1)
      setCursor(next); setInput(next < 0 ? '' : history[next] ?? '')
    }} /><button type="submit" aria-label="Executar comando"><Icon icon="key-enter" size={14} /></button></form>
    <div className="terminal-footer">Somente leitura · sem acesso ao sistema ou execução de código</div>
  </Dialog>
}
