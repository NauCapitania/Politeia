import { useEffect } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { NonIdealState, Spinner } from '@blueprintjs/core'
import { isStatic, useInstitutions } from './api/client'
import { useStore } from './store'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { Inspector } from './components/Inspector'
import { Sources } from './views/Sources'
import { SenadoHub } from './views/SenadoHub'
import { Stf } from './views/Stf'
import { Noticias } from './views/Noticias'
import { SenatorPanel } from './components/SenatorPanel'

const VIEWS = { senado: SenadoHub, stf: Stf, noticias: Noticias, sources: Sources }

export default function App() {
  const { data, isLoading, error } = useInstitutions()
  const { institutionId, setInstitution, view, senadoTab, selectedId, sidebarCollapsed } = useStore()

  useEffect(() => {
    if (!institutionId && data?.length) setInstitution(data.find((i) => i.id === 'ins_br_senado')?.id ?? data[0].id)
  }, [data, institutionId, setInstitution])

  const inst = data?.find((i) => i.id === institutionId)
  const View = VIEWS[view]

  return (
    <div className={`bp6-dark shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <TopBar current={inst} />
      <Sidebar inst={inst} />
      <main className="canvas">
        {isLoading && <div style={{ padding: 48 }}><Spinner size={24} /></div>}
        {error && <NonIdealState icon="offline" title={isStatic() ? 'Snapshot indisponível' : 'Engine API indisponível'} description={String(error)} />}
        {data && !data.length && (
          <NonIdealState icon="database" title="Nenhuma instituição registrada" description="Execute `python -m engine.cli sync`." />
        )}
        <AnimatePresence mode="wait">
          {inst && (
            <motion.div key={`${inst.id}:${view}:${view === 'senado' ? senadoTab : ''}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.18, ease: 'easeOut' }}>
              <View inst={inst} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      {(view === 'senado' && senadoTab === 'proposicoes') || view === 'sources' || !selectedId?.startsWith('per_') ? <Inspector inst={inst} /> : <SenatorPanel id={selectedId} />}
    </div>
  )
}
