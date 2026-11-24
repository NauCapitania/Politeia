import { useEffect, useState } from 'react'
import { Dialog, Icon, type IconName } from '@blueprintjs/core'
import { useSeats } from '../api/client'
import { useStore, type View, type SenadoTab } from '../store'

const DESTINATIONS: { label: string; detail: string; icon: IconName; view?: View; tab?: SenadoTab }[] = [
  { label: 'Central de situação', detail: 'Visão geral do observatório', icon: 'control', view: 'inicio' },
  { label: 'Composição do Senado', detail: 'Cadeiras, partidos e histórico', icon: 'layout-circle', tab: 'composicao' },
  { label: 'Votações', detail: 'Como votam os senadores', icon: 'series-search', tab: 'votacoes' },
  { label: 'Presidência 2025', detail: 'Resultado e inferências do voto secreto', icon: 'history', tab: 'presidencia2025' },
  { label: 'Presidência 2027', detail: 'Cenários e apoios', icon: 'predictive-analysis', tab: 'presidencia2027' },
  { label: 'Comissões', detail: 'Composição e presidências', icon: 'people', tab: 'comissoes' },
  { label: 'Proposições', detail: 'Pesquisar a atividade legislativa', icon: 'document', tab: 'proposicoes' },
  { label: 'STF e caso Master', detail: 'Evidências e caminhos institucionais', icon: 'take-action', view: 'stf' },
  { label: 'Notícias', detail: 'Últimas notícias coletadas', icon: 'feed', view: 'noticias' },
  { label: 'Fontes e cobertura', detail: 'Origem e limites dos dados', icon: 'database', view: 'sources' },
]
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

export function CommandPalette({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [date] = useState(() => new Date().toISOString().slice(0, 10))
  useEffect(() => { document.getElementById(`command-${active}`)?.scrollIntoView?.({ block: 'nearest' }) }, [active])
  const seats = useSeats(date)
  const { setView, setSenadoTab, setSearch, select } = useStore()
  const term = normalize(query.trim())
  const actions = DESTINATIONS.filter((d) => !term || normalize(`${d.label} ${d.detail}`).includes(term)).map((d) => ({
    label: d.label, detail: d.detail, icon: d.icon, run: () => d.tab ? setSenadoTab(d.tab) : setView(d.view!),
  }))
  if (term) {
    for (const s of (seats.data?.seats ?? []).filter((s) => normalize(`${s.name} ${s.full_name ?? ''} ${s.party} ${s.uf}`).includes(term)).slice(0, 6)) {
      actions.push({ label: s.name, detail: `${s.party ?? 'Sem partido'} · ${s.uf ?? ''} · Perfil do senador`, icon: 'person', run: () => { setSenadoTab('composicao'); select(s.person_id) } })
    }
    actions.push({ label: `Buscar proposições: “${query.trim()}”`, detail: 'Pesquisar na base legislativa', icon: 'search', run: () => { setSearch(query.trim()); setSenadoTab('proposicoes') } })
  }
  const execute = (i: number) => { actions[i]?.run(); onClose() }
  return <Dialog isOpen onClose={onClose} className="bp6-dark command-dialog" aria-label="Central de comandos">
    <div className="command-input"><Icon icon="search" size={18} /><input autoFocus aria-label="Buscar espaços, senadores ou proposições" placeholder="O que você quer investigar?" value={query} onChange={(e) => { setQuery(e.target.value); setActive(0) }}
      aria-controls="command-results" aria-activedescendant={`command-${active}`} role="combobox" aria-expanded="true" autoComplete="off"
      onKeyDown={(e) => {
        if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % actions.length) }
        if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + actions.length) % actions.length) }
        if (e.key === 'Enter') { e.preventDefault(); execute(active) }
      }} /><button onClick={onClose} aria-label="Fechar comandos"><kbd>Esc</kbd></button></div>
    <div className="command-caption">{term ? 'Resultados e ações' : 'Ir para um espaço de trabalho'}</div>
    <div className="command-results" id="command-results" role="listbox" aria-label="Resultados">{actions.map((a, i) => <button id={`command-${i}`} key={a.label} role="option" aria-selected={i === active} className={`command-option ${i === active ? 'active' : ''}`} onMouseEnter={() => setActive(i)} onClick={() => execute(i)}><Icon icon={a.icon} size={16} /><span><b>{a.label}</b><small>{a.detail}</small></span><Icon icon="key-enter" size={12} /></button>)}</div>
    <div className="command-footer"><span>↑ ↓ navegar · Enter abrir</span><span>Comandos locais · sem IA conectada</span></div>
  </Dialog>
}
