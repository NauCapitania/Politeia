import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useDragControls } from 'motion/react'
import { Button, Icon, TextArea } from '@blueprintjs/core'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useStore } from '../store'
import { askAgent, type ChartSpec, type NetworkSpec } from './client'
import { Grafico } from './Grafico'
import { Rede } from './Rede'

type Turn = { papel: 'usuario' | 'agente'; texto: string; graficos?: ChartSpec[]; redes?: NetworkSpec[]; passos?: string[]; erro?: boolean }

const STORAGE = 'politeia.agente.conversa'
const SUGESTOES = [
  'Quem deve ganhar a Presidência do Senado em 2027, e por quê?',
  'O caso Master vai dar em pizza? Quais as evidências?',
  'Faça um gráfico das bancadas por partido hoje.',
  'Como cada partido tende a votar num impeachment de ministro do STF?',
]
const TELAS: Record<string, string> = {
  composicao: 'Senado — composição', votacoes: 'Senado — votações', presidencia2025: 'Senado — Presidência 2025',
  presidencia2027: 'Senado — Presidência 2027', proposicoes: 'Senado — proposições', comissoes: 'Senado — comissões',
}

function load(): Turn[] {
  try { return JSON.parse(localStorage.getItem(STORAGE) ?? '[]') as Turn[] } catch { return [] }
}

export function Agente() {
  const { view, senadoTab, selectedId } = useStore()
  const [open, setOpen] = useState(false)
  const [wide, setWide] = useState(false)
  const [turns, setTurns] = useState<Turn[]>(load)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const drag = useDragControls()

  useEffect(() => {
    try { localStorage.setItem(STORAGE, JSON.stringify(turns.slice(-40))) } catch { /* histórico é opcional */ }
    scroller.current?.scrollTo?.({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => { if (open) input.current?.focus() }, [open])

  const patchLast = (fn: (t: Turn) => Turn) => setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])])

  async function send(text: string) {
    const pergunta = text.trim()
    if (!pergunta || busy) return
    const history = [...turns.filter((t) => !t.erro), { papel: 'usuario' as const, texto: pergunta }]
    setTurns([...turns, { papel: 'usuario', texto: pergunta }, { papel: 'agente', texto: '', passos: [], graficos: [], redes: [] }])
    setDraft('')
    setBusy(true)
    abort.current = new AbortController()
    try {
      await askAgent(
        history.map(({ papel, texto }) => ({ papel, texto })),
        { tela: view === 'senado' ? TELAS[senadoTab] : view, selecionado: selectedId },
        (event) => {
          if (event.tipo === 'passo') patchLast((t) => ({ ...t, passos: [...(t.passos ?? []), event.texto] }))
          else if (event.tipo === 'grafico') patchLast((t) => ({ ...t, graficos: [...(t.graficos ?? []), event.grafico] }))
          else if (event.tipo === 'rede') patchLast((t) => ({ ...t, redes: [...(t.redes ?? []), event.rede] }))
          else if (event.tipo === 'resposta') patchLast((t) => ({ ...t, texto: event.texto }))
          else patchLast((t) => ({ ...t, texto: event.texto, erro: true }))
        },
        abort.current.signal,
      )
    } catch (error) {
      if ((error as Error).name !== 'AbortError') patchLast((t) => ({ ...t, texto: 'Falha de conexão com o agente.', erro: true }))
      else patchLast((t) => ({ ...t, texto: t.texto || 'Interrompido.', erro: !t.texto }))
    } finally {
      setBusy(false)
      abort.current = null
    }
  }

  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button className="agente-launcher" onClick={() => setOpen(true)} aria-label="Abrir agente político"
            title="Agente político (Ctrl+J)" initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.6, opacity: 0 }} whileHover={{ scale: 1.06 }}>
            <span className="agente-orb" /><span>Agente</span><kbd>Ctrl J</kbd>
          </motion.button>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {open && (
          <motion.section className={`agente-janela ${wide ? 'wide' : ''}`} role="dialog" aria-label="Agente político"
            drag dragControls={drag} dragListener={false} dragMomentum={false}
            initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.97 }} transition={{ type: 'spring', stiffness: 380, damping: 32 }}>
            <header className="agente-head" onPointerDown={(e) => drag.start(e)}>
              <span className={`agente-orb ${busy ? 'busy' : ''}`} />
              <div className="agente-title">
                <strong>Agente político</strong>
                <span>{busy ? 'pesquisando…' : 'Gemini · lê os dados do Politeia e notícias'}</span>
              </div>
              <Button minimal small icon="trash" title="Nova conversa" aria-label="Nova conversa" disabled={busy || !turns.length}
                onClick={() => setTurns([])} />
              <Button minimal small icon={wide ? 'minimize' : 'maximize'} title={wide ? 'Reduzir' : 'Ampliar'}
                aria-label={wide ? 'Reduzir' : 'Ampliar'} onClick={() => setWide((w) => !w)} />
              <Button minimal small icon="cross" title="Fechar (Esc)" aria-label="Fechar agente" onClick={() => setOpen(false)} />
            </header>
            <div className="agente-corpo" ref={scroller}>
              {!turns.length && (
                <div className="agente-vazio">
                  <p>Pergunte sobre o Senado, o STF e o caso Master. O agente consulta os dados do app, pesquisa notícias e desenha gráficos.</p>
                  {SUGESTOES.map((s) => <button key={s} className="agente-sugestao" onClick={() => send(s)}>{s}</button>)}
                </div>
              )}
              {turns.map((t, i) => (
                <motion.div key={i} className={`agente-msg ${t.papel} ${t.erro ? 'erro' : ''}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                  {t.papel === 'agente' && !!t.passos?.length && (
                    <ul className="agente-passos">
                      {t.passos.map((p, j) => (
                        <li key={j} className={busy && i === turns.length - 1 && j === t.passos!.length - 1 && !t.texto ? 'ativo' : ''}>
                          <Icon icon={p.startsWith('Lendo') ? 'database' : p.startsWith('Pesquisando') ? 'search' : p.startsWith('Desenhando') ? 'chart' : p.startsWith('Montando') ? 'graph' : 'lightbulb'} size={11} />{p}
                        </li>
                      ))}
                    </ul>
                  )}
                  {t.graficos?.map((g, j) => <Grafico key={j} spec={g} />)}
                  {t.redes?.map((r, j) => <Rede key={j} spec={r} />)}
                  {t.texto && (t.papel === 'agente'
                    ? <div className="agente-md"><Markdown remarkPlugins={[remarkGfm]} components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>{t.texto}</Markdown></div>
                    : <p>{t.texto}</p>)}
                </motion.div>
              ))}
            </div>
            <form className="agente-entrada" onSubmit={(e) => { e.preventDefault(); void send(draft) }}>
              <TextArea inputRef={input} value={draft} placeholder="Pergunte ao agente…" rows={2} fill
                onChange={(e) => setDraft(e.target.value)} aria-label="Pergunta ao agente"
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(draft) } }} />
              {busy
                ? <Button icon="stop" onClick={() => abort.current?.abort()} aria-label="Parar" title="Parar" />
                : <Button type="submit" intent="primary" icon="send-message" disabled={!draft.trim()} aria-label="Enviar" title="Enviar (Enter)" />}
            </form>
            <p className="agente-aviso">Análises e previsões são inferência, não fato. Confira as fontes.</p>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  )
}
