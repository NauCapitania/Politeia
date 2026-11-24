import { Tab, Tabs } from '@blueprintjs/core'
import type { Institution } from '../api/client'
import { useStore, type SenadoTab } from '../store'
import { Senado } from './Senado'
import { Votacoes } from './Votacoes'
import { Presidencia2025 } from './Presidencia2025'
import { Presidencia2027 } from './Presidencia2027'
import { Proposals } from './Proposals'
import { Comissoes } from './Comissoes'

const TABS: { id: SenadoTab; title: string }[] = [
  { id: 'composicao', title: 'Composição' },
  { id: 'votacoes', title: 'Votações' },
  { id: 'presidencia2025', title: 'Presidência 2025' },
  { id: 'presidencia2027', title: 'Presidência 2027' },
  { id: 'comissoes', title: 'Comissões' },
  { id: 'proposicoes', title: 'Proposições' },
]

export function SenadoHub({ inst }: { inst: Institution }) {
  const { senadoTab, setSenadoTab } = useStore()
  const body = {
    composicao: <Senado />, votacoes: <Votacoes />, presidencia2025: <Presidencia2025 />,
    presidencia2027: <Presidencia2027 />, comissoes: <Comissoes />, proposicoes: <Proposals inst={inst} />,
  }[senadoTab]
  return (
    <div>
      <div className="subnav">
        <Tabs id="senado-tabs" selectedTabId={senadoTab} onChange={(t) => setSenadoTab(t as SenadoTab)} large={false}>
          {TABS.map((t) => <Tab key={t.id} id={t.id} title={t.title} />)}
        </Tabs>
      </div>
      {body}
    </div>
  )
}
