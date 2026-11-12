import { useEffect } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { NonIdealState, Spinner } from '@blueprintjs/core'
import { useInstitutions } from './api/client'
import { useStore } from './store'
import { TopBar } from './components/TopBar'
import { Sidebar } from './components/Sidebar'
import { Inspector } from './components/Inspector'
import { Overview } from './views/Overview'
import { People } from './views/People'
import { Proposals } from './views/Proposals'
import { GraphView } from './views/GraphView'
import { Sources } from './views/Sources'

const VIEWS = { overview: Overview, people: People, proposals: Proposals, graph: GraphView, sources: Sources }

export default function App() {
  const { data, isLoading, error } = useInstitutions()
  const { institutionId, setInstitution, view } = useStore()

  useEffect(() => {
    if (!institutionId && data?.length) setInstitution(data[0].id)
  }, [data, institutionId, setInstitution])

  const inst = data?.find((i) => i.id === institutionId)
  const View = VIEWS[view]

  return (
    <div className="bp6-dark shell">
      <TopBar institutions={data ?? []} current={inst} />
      <Sidebar inst={inst} />
      <main className="canvas">
        {isLoading && <div style={{ padding: 48 }}><Spinner size={24} /></div>}
        {error && <NonIdealState icon="offline" title="Engine API indisponível" description={String(error)} />}
        {data && !data.length && (
          <NonIdealState icon="database" title="Nenhuma instituição registrada" description="Execute `python -m engine.cli sync`." />
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
      <Inspector inst={inst} />
    </div>
  )
}
