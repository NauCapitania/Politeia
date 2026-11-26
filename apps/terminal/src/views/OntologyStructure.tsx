import { useState, type CSSProperties } from 'react'
import type { Body, Ontology } from '../api/ontology'
import './structure.css'

type Props = { data: Ontology; focus: string; onExplore: (id: string) => void }
const COLORS: Record<string, string> = { pow_legislativo: 'var(--atlas-leg)', pow_executivo: 'var(--atlas-exec)', pow_judiciario: 'var(--atlas-jud)', grp_funcoes_justica: 'var(--atlas-ctrl)' }
const PRIORITY = ['bod_congresso', 'bod_presidencia', 'bod_stf', 'bod_stj', 'bod_tse', 'bod_tst', 'bod_stm', 'bod_cnj']

function ordered(bodies: Body[]) {
  return [...bodies].sort((a, b) => {
    const rank = (b: Body) => PRIORITY.includes(b.id) ? PRIORITY.indexOf(b.id) : b.origin === 'curated' ? 20 : 30
    return rank(a) - rank(b) || a.name.localeCompare(b.name, 'pt-BR')
  })
}

export function OntologyStructure({ data, focus, onExplore }: Props) {
  const selectedBody = data.offices.find((o) => o.id === focus)?.body_id ?? focus
  const path = new Set<string>()
  let current = data.bodies.find((b) => b.id === selectedBody)
  while (current && !path.has(current.id)) {
    path.add(current.id)
    current = data.bodies.find((b) => b.id === current!.parent_id)
  }
  const roots = (powerId: string) => ordered(data.bodies.filter((b) => b.power_id === powerId && !data.bodies.some((p) => p.id === b.parent_id && p.power_id === powerId)))
  const unassignedOffices = data.offices.filter((o) => !data.bodies.some((b) => b.id === o.body_id))
  return <div className="structure">
    <header className="structure-union"><span>ESTRUTURA FEDERAL</span><h2>União</h2><p>Selecione um órgão para consultar cargos, ocupantes e competências.</p></header>
    <div className="structure-powers" aria-label="Três poderes constitucionais">
      {data.powers.filter((p) => p.constitutional).map((p, index) => <section className="structure-power" key={p.id} style={{ '--branch-color': COLORS[p.id] } as CSSProperties} aria-label={`Poder ${p.name}`}>
        <header><span className="structure-number">0{index + 1}</span><button aria-label={`Explorar ${p.name}`} aria-current={focus === p.id ? 'true' : undefined} onClick={() => onExplore(p.id)}><h3>{p.name}</h3><small>{data.bodies.filter((b) => b.power_id === p.id).length} órgãos na base</small></button></header>
        <ul className="structure-roots">{roots(p.id).map((b) => <Branch key={b.id} body={b} data={data} focus={focus} path={path} depth={0} onExplore={onExplore} />)}</ul>
      </section>)}
    </div>
    {data.powers.filter((p) => !p.constitutional).map((p) => <section className="structure-autonomous" key={p.id} style={{ '--branch-color': COLORS[p.id] } as CSSProperties} aria-label={p.name}>
      <header><h3>{p.name}</h3><p>Instituições autônomas. Não constituem um quarto poder.</p></header>
      <ul className="structure-roots">{roots(p.id).map((b) => <Branch key={b.id} body={b} data={data} focus={focus} path={path} depth={0} onExplore={onExplore} />)}</ul>
    </section>)}
    {!!unassignedOffices.length && <section className="structure-unassigned" aria-label="Cargos sem órgão específico"><h3>Cargos</h3><p>Sem órgão específico associado na base.</p><ul className="structure-offices">{unassignedOffices.map((o) => <li key={o.id}><button aria-label={`Explorar ${o.name}`} aria-current={focus === o.id ? 'true' : undefined} onClick={() => onExplore(o.id)}>{o.name}<small>Cargo · {o.holders} {o.holders === 1 ? 'ocupante' : 'ocupantes'}</small></button></li>)}</ul></section>}
    <p className="structure-note">As ramificações seguem os vínculos da base. O TCU é agrupado no Legislativo para leitura, sem subordinação ao Congresso.</p>
  </div>
}

function Branch({ body, data, focus, path, depth, onExplore }: { body: Body; path: Set<string>; depth: number } & Props) {
  const [expanded, setExpanded] = useState(depth === 0)
  const [showAll, setShowAll] = useState(false)
  // Include the selected route even if it was not among the first visible children.
  const routeChildren = ordered(data.bodies.filter((b) => b.parent_id === body.id && b.power_id === body.power_id))
  const ancestor = path.has(body.id) && body.id !== (data.offices.find((o) => o.id === focus)?.body_id ?? focus)
  const open = expanded || ancestor
  const visible = routeChildren.filter((b, i) => showAll || i < 5 || path.has(b.id))
  const offices = data.offices.filter((o) => o.body_id === body.id)
  const selected = body.id === focus || offices.some((o) => o.id === focus)
  return <li className={`structure-branch ${selected ? 'selected' : ''}`}>
    <div className="structure-row">
      {routeChildren.length ? <button className="structure-toggle" aria-label={`${open ? 'Recolher' : 'Expandir'} órgãos de ${body.name}`} aria-expanded={open} onClick={() => { setExpanded(!open); if (ancestor) onExplore(body.id) }}>{open ? '−' : '+'}</button> : <span className="structure-leaf" aria-hidden="true" />}
      <button className="structure-body" aria-label={`Explorar ${body.name}`} aria-current={body.id === focus ? 'true' : undefined} onClick={() => onExplore(body.id)}><span>{body.name}</span>{body.acronym && <small>{body.acronym}</small>}</button>
    </div>
    {body.id === 'bod_tcu' && <small className="structure-body-note">Órgão autônomo · CF, art. 71</small>}
    {selected && !!offices.length && <ul className="structure-offices">{offices.map((o) => <li key={o.id}><button aria-label={`Explorar ${o.name}`} aria-current={focus === o.id ? 'true' : undefined} onClick={() => onExplore(o.id)}>{o.name}<small>Cargo · {o.holders} ocupantes</small></button></li>)}</ul>}
    {open && !!routeChildren.length && <ul className="structure-children">{visible.map((b) => <Branch key={b.id} body={b} data={data} focus={focus} path={path} depth={depth + 1} onExplore={onExplore} />)}
      {(showAll || routeChildren.length > visible.length) && <li className="structure-more"><button aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>{showAll ? 'Mostrar menos' : `Mostrar outros ${routeChildren.length - visible.length} órgãos`}</button></li>}
    </ul>}
  </li>
}
