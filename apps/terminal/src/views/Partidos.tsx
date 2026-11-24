import { Callout, Spinner } from '@blueprintjs/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { SrcList } from '../components/SrcList'
import { dateLabel, type Analysis, type PartyDossier } from './partidos/data'
import { Funds } from './partidos/Funds'
import { Lineage } from './partidos/Lineage'
import './partidos/partidos.css'

const panels = { historico: 'Histórico', fundos: 'Financiamento', fontes: 'Sites partidários' } as const

function Note({ item }: { item: Analysis }) {
  return <article className="partidos-panel">
    <p className="partidos-kicker">{item.section === 'coverage' ? 'Metodologia' : 'Análise e interpretação'}</p>
    <h3>{item.title}</h3>
    <p>{item.text}</p>
    <SrcList sources={item.sources} />
  </article>
}

export function Partidos() {
  const [panel, setPanel] = useState<keyof typeof panels>('historico')
  const query = useQuery({ queryKey: ['dossier', 'partidos'], queryFn: () => api<PartyDossier | null>('/dossies/partidos') })
  const doc = query.data
  const items = doc?.items
  return <div className="view partidos">
    <header className="partidos-hero">
      <p className="partidos-kicker">Observatório partidário</p>
      <h1>Partidos</h1>
      <p>Da ditadura à configuração atual: acompanhe origens, mudanças de sigla, fusões, federações e a distribuição dos fundos públicos.</p>
      {doc && <div className="partidos-hero-meta">
        <span>{items?.event.length} marcos históricos</span><span>Curadoria em {dateLabel(doc.as_of)}</span>
      </div>}
    </header>
    {query.isPending ? <div role="status" aria-label="Carregando dossiê de partidos"><Spinner size={24} /></div> :
      !doc || !items ? <Callout intent="warning">Dossiê de partidos indisponível nesta versão dos dados.</Callout> : <>
        <nav className="partidos-tabs" aria-label="Seções de Partidos">
          {Object.entries(panels).map(([id, title]) =>
            <button key={id} type="button" aria-pressed={id === panel} onClick={() => setPanel(id as keyof typeof panels)}>
              {title}
            </button>)}
        </nav>
        {panel === 'historico' && <div className="partidos-stack">
          <Lineage parties={items.party} events={items.event} asOf={doc.as_of} />
          {items.analysis?.filter(item => item.section === 'coverage').map(item => <Note key={item.id} item={item} />)}
        </div>}
        {panel === 'fundos' && <div className="partidos-stack">
          <Funds funding={items.funding} parties={items.party} comparisons={items.comparison ?? []} />
          {items.analysis?.filter(item => !item.section).map(item => <Note key={item.id} item={item} />)}
        </div>}
        {panel === 'fontes' && <div className="partidos-stack">
          {items.analysis?.filter(item => item.section === 'sites').map(item => <Note key={item.id} item={item} />)}
          <section className="partidos-panel">
            <h2>Auditoria de 10 sites partidários</h2>
            <p>Amostra das páginas públicas localizadas; não é uma avaliação da completude ou da atualidade de cada site.</p>
            <div className="partidos-sites">{items.site?.map(site => <article key={site.id}>
              <h3>{site.title}</h3><p>{site.text}</p><SrcList sources={site.sources} />
            </article>)}</div>
          </section>
        </div>}
      </>}
  </div>
}
