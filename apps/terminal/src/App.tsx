import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, MotionConfig } from 'motion/react'
import { NonIdealState, Spinner } from '@blueprintjs/core'
import { useInstitutions } from './api/client'
import { useStore } from './store'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { Inspector } from './components/Inspector'
import { Sources } from './views/Sources'
import { SenadoHub } from './views/SenadoHub'
import { Stf } from './views/Stf'
import { Noticias } from './views/Noticias'
import { SenatorPanel } from './components/SenatorPanel'
import { Overview } from './views/Overview'
import { CommandPalette } from './components/CommandPalette'
import { StatusBar } from './components/StatusBar'
import { LocalTerminal } from './components/LocalTerminal'
import { useTheme } from './useTheme'

const VIEWS = { inicio: Overview, senado: SenadoHub, stf: Stf, noticias: Noticias, sources: Sources }

export default function App() {
  const { theme, toggleTheme } = useTheme()
  const { data, isLoading, error } = useInstitutions()
  const { institutionId, setInstitution, view, senadoTab, selectedId, sidebarCollapsed } = useStore()
  const [commandOpen, setCommandOpen] = useState(false)
  const [terminalOpen, setTerminalOpen] = useState(false)
  const canvas = useRef<HTMLElement>(null)

  useEffect(() => { if (canvas.current) canvas.current.scrollTop = 0 }, [view, senadoTab])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setTerminalOpen(false); setCommandOpen((open) => !open) }
      if (e.key === 'Escape' && !commandOpen && !terminalOpen) useStore.getState().select(null)
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [commandOpen, terminalOpen])

  useEffect(() => {
    if (!institutionId && data?.length) setInstitution(data.find((i) => i.id === 'ins_br_senado')?.id ?? data[0].id)
  }, [data, institutionId, setInstitution])

  const inst = data?.find((i) => i.id === institutionId)
  const View = VIEWS[view]

  return (
    <MotionConfig reducedMotion="user"><div className={`shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <a className="skip-link" href="#workspace">Pular para o conteúdo</a>
      <TopBar current={inst} onCommand={() => setCommandOpen(true)} onTerminal={() => setTerminalOpen(true)} theme={theme} onTheme={toggleTheme} />
      <Sidebar inst={inst} onTerminal={() => setTerminalOpen(true)} />
      <main className="canvas" id="workspace" tabIndex={-1} ref={canvas}>
        {isLoading && <div style={{ padding: 48 }}><Spinner size={24} /></div>}
        {error && <NonIdealState icon="offline" title="Não foi possível carregar a base" description="Os dados estão indisponíveis nesta consulta. Tente novamente em instantes." />}
        {data && !data.length && (
          <NonIdealState icon="database" title="Seu observatório está sendo preparado" description="As instituições aparecerão após a primeira coleta de dados." />
        )}
        <AnimatePresence mode="wait">
          {inst && (
            <motion.div key={`${inst.id}:${view}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: 'easeOut' }}>
              <View inst={inst} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      <AnimatePresence>{selectedId && <motion.section className="evidence-window" key="evidence" aria-label="Painel de evidências" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }}>
        <div className="evidence-titlebar"><span>INSPEÇÃO / EVIDÊNCIAS</span><button onClick={() => useStore.getState().select(null)} aria-label="Fechar painel de evidências">Fechar · Esc</button></div>
        {(view === 'senado' && senadoTab === 'proposicoes') || view === 'sources' || !selectedId.startsWith('per_') ? <Inspector inst={inst} /> : <SenatorPanel id={selectedId} />}
      </motion.section>}</AnimatePresence>
      <StatusBar onCommand={() => setCommandOpen(true)} />
      {commandOpen && <CommandPalette onClose={() => setCommandOpen(false)} />}
      {terminalOpen && <LocalTerminal onClose={() => setTerminalOpen(false)} />}
    </div></MotionConfig>
  )
}
