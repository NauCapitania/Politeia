import { useState } from 'react'
import { Icon, Spinner } from '@blueprintjs/core'
import { useOntology, useObservedLinks, competenceBody, type Ontology, type Competence } from '../api/ontology'
import { useSnapshotMeta } from '../api/client'
import { useStore, type View } from '../store'
import { fmtDate, fmtDateTime } from '../format'
import { SrcList } from '../components/SrcList'
import { OntologyMap, type MapNode } from './OntologyMap'
import { CommitteeMembers } from './OntologyCommittee'
import './ontology.css'

type Lens = 'estrutura' | 'competencias' | 'ana_caso_master' | 'ana_presidencia_2027'
const MODULES: Record<string, View> = { bod_congresso: 'congresso', bod_senado: 'senado', bod_camara: 'camara', bod_stf: 'stf', bod_presidencia: 'executivo' }
const PROVISION: Record<string, string> = { direct_election: 'Eleição direta', elected_by_peers: 'Eleição pelos pares', nominated_and_approved: 'Indicação e aprovação', free_appointment: 'Livre nomeação', party_indication: 'Indicação partidária' }

export function Overview() {
  const q = useOntology()
  return <div className="view ontology-home">
    <header className="atlas-heading"><div><div className="eyebrow"><span className="dot ok" /> UNIÃO · QUADRO ATUAL</div><h1>Ontologia da política brasileira</h1><p>Órgãos, cargos, ocupantes e competências da União.</p></div><span className="atlas-now">FONTES OFICIAIS <span className="dot ok" /></span></header>
    {q.isLoading && <div role="status" className="atlas-state"><Spinner size={24} /><p>Construindo o mapa da União…</p></div>}
    {q.isError && <div role="alert" className="atlas-state"><h2>O mapa está indisponível nesta consulta.</h2><button onClick={() => q.refetch()}>Tentar novamente</button></div>}
    {q.data && (q.data.powers?.length ? <Atlas data={q.data} /> : <p className="atlas-state">A ontologia da União ainda não foi carregada.</p>)}
  </div>
}

function Atlas({ data }: { data: Ontology }) {
  const [focus, setFocus] = useState('uniao')
  const [lens, setLens] = useState<Lens>('estrutura')
  const [search, setSearch] = useState('')
  const [personSearch, setPersonSearch] = useState('')
  const [page, setPage] = useState(0)
  const [selectedCompetence, setSelectedCompetence] = useState<string | null>(null)
  const [behavior, setBehavior] = useState(false)
  const [personId, setPersonId] = useState<string | null>(null)
  const { setView, setAnalysis, setSenadoTab } = useStore()
  const meta = useSnapshotMeta()
  const power = data.powers.find((p) => p.id === focus)
  const office = data.offices.find((o) => o.id === focus)
  const body = data.bodies.find((b) => b.id === (office?.body_id ?? focus))
  const institution = body?.institution_id
  const observed = useObservedLinks(behavior ? institution : null)
  const analysis = data.analyses.find((a) => a.id === lens)
  const analysisIds = new Set(analysis?.entities.flatMap((e) => [e.entity_id, data.offices.find((o) => o.id === e.entity_id)?.body_id ?? '']) ?? [])
  const activeCompetences = data.competences.filter((c) => !analysis || analysisIds.has(c.id))
  const selected = data.competences.find((c) => c.id === selectedCompetence)
  const scopedCompetences = office ? data.competences.filter((c) => c.holder_office_id === focus || c.target_office_id === focus) : body ? data.competences.filter((c) => competenceBody(data, c, 'holder') === body.id || competenceBody(data, c, 'target') === body.id) : power ? activeCompetences.filter((c) => data.bodies.some((b) => b.power_id === power.id && b.id === competenceBody(data, c, 'holder'))) : activeCompetences
  const competences = selected ? [selected, ...scopedCompetences.filter((c) => c.id !== selected.id)] : scopedCompetences
  const children = data.bodies.filter((b) => power ? b.power_id === power.id && (!b.parent_id || data.bodies.find((p) => p.id === b.parent_id)?.power_id !== power.id) : b.parent_id === focus)
  const offices = data.offices.filter((o) => o.body_id === body?.id)
  const holdings = data.holdings.filter((h) => (office ? h.office_id === focus : h.body_id === body?.id) && (h.person_name ?? '').toLocaleLowerCase('pt-BR').includes(personSearch.toLocaleLowerCase('pt-BR')))
  function go(id: string) { setFocus(id); setPersonSearch(''); setSearch(''); setPage(0); setPersonId(null); setSelectedCompetence(null); setBehavior(false) }
  const title = office?.name ?? body?.name ?? power?.name ?? 'União'
  const legal = data.legal_bases.find((b) => b.id === (office?.legal_basis_id ?? body?.legal_basis_id))
  const focusedPower = body?.power_id ?? power?.id ?? ''
  const nodes: MapNode[] = []
  if (focus === 'uniao') {
    nodes.push({ id: 'uniao', name: 'União', short: 'BR', kind: 'Estado brasileiro', power: '', x: 500, y: 445, detail: 'Poderes e órgãos federais' })
    data.powers.filter((p) => p.constitutional).forEach((p, i) => {
      const a = (-90 + i * 120) * Math.PI / 180
      const count = data.bodies.filter((b) => b.power_id === p.id).length
      nodes.push({ id: p.id, name: p.name, short: ['LEG', 'EXE', 'JUD'][i], kind: 'Poder constitucional', power: p.id, x: 500 + Math.cos(a) * 180, y: 445 + Math.sin(a) * 180, detail: `${count} ${count === 1 ? 'órgão mapeado' : 'órgãos mapeados'}` })
      const bodies = data.bodies.filter((b) => b.power_id === p.id && b.origin === 'curated')
      bodies.forEach((b, j) => {
        const angle = a + (bodies.length === 1 ? 0 : (j / (bodies.length - 1) - .5) * 1.32)
        const radius = j % 2 ? 390 : 315
        nodes.push({ id: b.id, name: b.name, short: b.acronym ?? b.name.split(' ').map((s) => s[0]).join('').slice(0, 5), kind: 'Órgão', power: p.id, x: 500 + Math.cos(angle) * radius, y: 445 + Math.sin(angle) * radius, detail: b.seats ? `${b.seats} cadeiras previstas` : 'Explorar competências' })
      })
    })
    data.powers.filter((p) => !p.constitutional).forEach((p) => {
      nodes.push({ id: p.id, name: p.name, short: 'CF · arts. 127–135', kind: 'Instituições autônomas', power: p.id, x: 500, y: 935, detail: 'Ministério Público e Defensoria Pública' })
      data.bodies.filter((b) => b.power_id === p.id && b.origin === 'curated').forEach((b, i) => nodes.push({ id: b.id, name: b.name, short: b.acronym ?? '', kind: 'Órgão', power: p.id, x: 300 + i * 400, y: 1030, detail: 'Instituição autônoma' }))
    })
  } else {
    nodes.push({ id: focus, name: title, short: office ? 'Cargo' : body?.acronym ?? power?.name.slice(0, 3) ?? '', kind: office ? 'Cargo' : body ? 'Órgão' : power?.constitutional ? 'Poder constitucional' : 'Instituições autônomas', power: focusedPower, x: 500, y: 445, detail: 'Você está aqui' })
    const ids = new Set([...(office?.body_id ? [office.body_id] : body?.parent_id ? [body.parent_id] : []), ...children.map((b) => b.id), ...(!office ? offices.map((o) => o.id) : [])])
    competences.forEach((c) => { const a = competenceBody(data, c, 'holder'); const b = competenceBody(data, c, 'target'); if (a && a !== body?.id) ids.add(a); if (b && b !== body?.id) ids.add(b) })
    // A selected connection must keep both endpoints, even in a crowded layer.
    const endpoints = selected ? [competenceBody(data, selected, 'holder'), competenceBody(data, selected, 'target')].filter((id): id is string => !!id) : []
    const neighbors = [...new Set([...endpoints, ...ids])].filter((id) => id !== focus).slice(0, 10)
    neighbors.forEach((id, i) => {
      const b = data.bodies.find((b) => b.id === id); const o = data.offices.find((o) => o.id === id)
      const a = -Math.PI / 2 + i * Math.PI * 2 / neighbors.length
      nodes.push({ id, name: b?.name ?? o?.name ?? id, short: b?.acronym ?? (o ? 'Cargo' : ''), kind: b ? 'Órgão' : 'Cargo', power: b?.power_id ?? focusedPower, x: 500 + Math.cos(a) * 350, y: 445 + Math.sin(a) * 325, detail: b ? 'Explorar órgão' : `${o?.holders ?? 0} ocupantes na base` })
    })
  }
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const edges: { id: string; a: string; b: string; competence?: Competence }[] = []
  if (lens === 'estrutura' && !selected) {
    nodes.forEach((n) => {
      if (n.id === focus || n.kind === 'Instituições autônomas') return
      const b = data.bodies.find((b) => b.id === n.id)
      // Only draw real containment, never turn a competence into a parent-child relationship.
      const parent = b ? b.parent_id : data.offices.find((o) => o.id === n.id)?.body_id
      const source = focus === 'uniao' ? (b ? nodeById.has(parent ?? '') ? parent! : b.power_id : 'uniao') : power && b?.power_id === power.id ? focus : parent
      if (source && nodeById.has(source)) edges.push({ id: n.id, a: source, b: n.id })
    })
  }
  {
    (selected ? [selected] : activeCompetences).forEach((c) => {
      const a = competenceBody(data, c, 'holder'); const b = competenceBody(data, c, 'target')
      const from = office && c.holder_office_id === focus ? focus : a
      const to = office && c.target_office_id === focus ? focus : b
      if (from && to && from !== to && nodeById.has(from) && nodeById.has(to)) edges.push({ id: c.id, a: from, b: to, competence: c })
    })
  }
  const matches = search.trim() ? [...data.bodies, ...data.offices].filter((n) => n.name.toLocaleLowerCase('pt-BR').includes(search.trim().toLocaleLowerCase('pt-BR'))).slice(0, 20) : []
  const links = [...(observed.data?.links ?? [])].filter((l) => !personId || l.a === personId || l.b === personId).sort((a, b) => b.weight - a.weight || b.shared - a.shared).slice(0, 10)
  const personName = (id: string) => data.holdings.find((h) => h.person_id === id)?.person_name ?? 'Pessoa sem nome na base'
  return <>
    <div className="atlas-toolbar"><div className="atlas-lenses" aria-label="Lentes do mapa">{([['estrutura', 'Estrutura'], ['competencias', 'Competências'], ['ana_caso_master', 'Caso Master'], ['ana_presidencia_2027', 'Senado 2027']] as const).map(([id, label]) => <button key={id} aria-pressed={lens === id} onClick={() => { setLens(id); setSelectedCompetence(null); if (id.startsWith('ana_')) go('uniao') }}>{label}</button>)}</div><label className="atlas-search"><Icon icon="search" size={13} /><input aria-label="Buscar órgão ou cargo" placeholder="Encontrar órgão ou cargo…" value={search} onChange={(e) => setSearch(e.target.value)} /></label></div>
    {search.trim() && <div className="atlas-search-results" aria-label="Resultados da busca">{matches.length ? matches.map((n) => <button key={n.id} onClick={() => go(n.id)}>{n.name}<span>Explorar ↗</span></button>) : <p>Nenhum órgão ou cargo encontrado.</p>}</div>}
    <div className="atlas-workspace">
      <section className="atlas-map" aria-label="Mapa interativo da União">
        <nav className="atlas-breadcrumbs" aria-label="Camadas da ontologia"><button onClick={() => go('uniao')}>União</button>{focus !== 'uniao' && <><span>/</span>{focusedPower && focusedPower !== focus && <><button onClick={() => go(focusedPower)}>{data.powers.find((p) => p.id === focusedPower)?.name}</button><span>/</span></>}{office && body && <><button onClick={() => go(body.id)}>{body.acronym ?? body.name}</button><span>/</span></>}<span aria-current="page">{title}</span></>}</nav>
        <div className="atlas-map-caption"><span>{analysis ? 'LEITURA TEMÁTICA' : focus === 'uniao' ? '01 / VISÃO DO ESTADO' : office ? '03 / CARGOS E PESSOAS' : '02 / DENTRO DA ESTRUTURA'}</span><span>Selecione para explorar ↗</span></div>
        {analysis && <div className="atlas-lens-note">{analysis.title}: os destaques indicam relações institucionais da análise, não responsabilidade pessoal.</div>}
        <OntologyMap nodes={nodes} edges={edges} focus={focus} analysisIds={analysis ? analysisIds : null} onExplore={go} selectedCompetence={selectedCompetence} onCompetence={(id) => { setSelectedCompetence(id); setLens('competencias') }} />
        <footer className="atlas-map-footer"><span><i />Pontilhado: estrutura · linha: competência legal →</span><span>Selecione uma conexão para entender</span></footer>
      </section>
      <aside className="atlas-inspect" aria-label="Detalhes da ontologia">
        <div className="atlas-inspect-head"><div className="eyebrow">{office ? 'CARGO' : body ? 'ÓRGÃO' : power ? power.constitutional ? 'PODER' : 'FUNÇÕES ESSENCIAIS À JUSTIÇA' : 'UNIÃO'}</div><h2>{title}</h2><p>{office?.description ?? body?.description ?? power?.description ?? 'Selecione um poder ou órgão para consultar suas competências, cargos e ocupantes. As linhas indicam relações previstas em lei.'}</p>{legal && <a className="atlas-legal" href={legal.url} target="_blank" rel="noreferrer">{legal.norm} · {legal.provision} ↗</a>}{MODULES[body?.id ?? ''] && <button className="atlas-module" onClick={() => setView(MODULES[body!.id])}>Abrir espaço da instituição ↗</button>}</div>
        {focus === 'uniao' && <div className="atlas-intro"><div><b>{data.bodies.length.toLocaleString('pt-BR')}</b><span>órgãos mapeados</span></div><div><b>{data.competences.length}</b><span>competências legais</span></div><p>Três poderes: Legislativo, Executivo e Judiciário. MP e Defensoria são instituições autônomas, apresentadas separadamente. O mapa destaca órgãos selecionados; a busca inclui toda a base.</p></div>}
        {power && !power.constitutional && <p className="atlas-note">Não é um quarto poder. Os vínculos administrativos são preservados.</p>}
        {!!children.length && <details className="atlas-section" open><summary>Órgãos nesta camada <span>{children.length}</span></summary><div className="atlas-children">{children.map((b) => <button key={b.id} onClick={() => go(b.id)}>{b.name}<span>↗</span></button>)}</div></details>}
        {!office && !!offices.length && <details className="atlas-section" open><summary>Cargos <span>{offices.length}</span></summary>{offices.map((o) => <button className="atlas-list-button" key={o.id} onClick={() => go(o.id)}><span>{o.name}<small>{o.holders} ocupantes registrados{o.seats ? ` · ${o.seats} vagas previstas` : ''}</small></span>↗</button>)}</details>}
        {office && <div className="atlas-section"><h3>Como se chega ao cargo</h3><p>{PROVISION[office.provision] ?? 'Forma de provimento não informada'}{office.term_years ? ` · mandato de ${office.term_years} anos` : ''}</p></div>}
        {body?.committee_id && !office && <CommitteeMembers key={body.id} id={body.committee_id} camara={body.parent_id === 'bod_camara'} />}
        {(body || office) && !body?.committee_id && <details className="atlas-section" open><summary>Ocupantes na base <span>{holdings.length}</span></summary><input className="atlas-person-search" aria-label="Buscar ocupante" placeholder="Buscar pessoa…" value={personSearch} onChange={(e) => { setPersonSearch(e.target.value); setPage(0) }} />{!holdings.length && <p>Nenhum ocupante encontrado nesta camada. Isso não significa cargo vago.</p>}{holdings.slice(page * 12, (page + 1) * 12).map((h) => <article className="atlas-person" key={h.id}><button onClick={() => setPersonId(personId === h.person_id ? null : h.person_id)} aria-expanded={personId === h.person_id}><strong>{h.person_name ?? 'Nome não informado'}</strong><small>{data.offices.find((o) => o.id === h.office_id)?.name} · {[h.party, h.represented_unit].filter(Boolean).join(' · ')}</small></button>{personId === h.person_id && <><p>{h.nominated_by && <>Indicação: {h.nominated_by}<br /></>}{h.since && <>{h.origin === 'mandate' ? 'Início do mandato' : 'Data de início registrada'}: {fmtDate(h.since)}</>}</p><SrcList sources={h.sources} hidePress /></>}</article>)}{holdings.length > 12 && <div className="atlas-pager"><button disabled={!page} onClick={() => setPage(page - 1)}>Anterior</button><span>{page * 12 + 1}–{Math.min((page + 1) * 12, holdings.length)}</span><button disabled={(page + 1) * 12 >= holdings.length} onClick={() => setPage(page + 1)}>Próxima</button></div>}</details>}
        <details className="atlas-section" open><summary>Competências e conexões <span>{competences.length}</span></summary>{!competences.length && <p>Não há competências detalhadas nesta camada da base.</p>}{competences.map((c) => { const from = competenceBody(data, c, 'holder'); const to = competenceBody(data, c, 'target'); const law = data.legal_bases.find((b) => b.id === c.legal_basis_id); return <article className={`atlas-competence ${selectedCompetence === c.id ? 'selected' : ''}`} key={c.id}><button className="atlas-competence-action" aria-pressed={selectedCompetence === c.id} onClick={() => { setSelectedCompetence(selectedCompetence === c.id ? null : c.id); setLens('competencias') }}><span>{data.offices.find((o) => o.id === c.holder_office_id)?.name ?? data.bodies.find((b) => b.id === from)?.name}</span><strong>{c.verb} →</strong><span>{c.target_label}</span></button>{c.description && <p>{c.description}</p>}{c.quorum && <p className="atlas-quorum">Quórum: {c.quorum}</p>}{law && <a className="atlas-legal" href={law.url} target="_blank" rel="noreferrer">{law.norm} · {law.provision}{c.provision ? ` · ${c.provision}` : ''} ↗</a>}<div className="atlas-jump">{from && from !== body?.id && <button onClick={() => go(c.holder_office_id ?? from)}>Quem decide ↗</button>}{to && to !== body?.id && <button onClick={() => go(c.target_office_id ?? to)}>Explorar destino ↗</button>}</div></article> })}</details>
        {institution && ['ins_br_senado', 'ins_br_camara'].includes(institution) && <div className="atlas-section"><button className="atlas-module" aria-expanded={behavior} onClick={() => setBehavior(!behavior)}>Votos em comum ↗</button>{behavior && <><p>Concordância em votações nominais abertas. Não é aliança declarada; votos secretos não entram.</p>{observed.isLoading && <Spinner size={18} />}{observed.isError && <p role="alert">Não foi possível carregar as ligações observadas.</p>}{observed.data && !links.length && <p>Sem ligações observadas nesta consulta.</p>}{links.map((l) => <div className="atlas-observed" key={`${l.a}-${l.b}`}><span>{personName(l.a)} ↔ {personName(l.b)}</span><b>{Math.round(l.weight * 100)}%</b><small>{l.shared} votações em comum</small></div>)}</>}</div>}
      </aside>
    </div>
    <section className="atlas-analyses" aria-label="Análises de exemplo"><div><div className="eyebrow">ANÁLISES DE EXEMPLO</div><h2>Processos e disputas institucionais</h2></div><button onClick={() => setAnalysis('caso-master')}><span>01 / ANÁLISE</span><strong>Caso Master ↗</strong><small>Competências da PF, PGR, STF, Banco Central e Senado.</small></button><button onClick={() => setSenadoTab('presidencia2027')}><span>02 / ANÁLISE</span><strong>Presidência do Senado 2027 ↗</strong><small>Composição do Senado, eleição da Mesa e atribuições da Presidência.</small></button><button className="atlas-all" onClick={() => setView('analises')}>Todas as análises →</button></section>
    <p className="atlas-provenance">Quadro atual da União · fontes legais nas conexões · ausência de informação não é ausência de vínculo.{meta.data && <> Snapshot gerado em {fmtDateTime(meta.data.generated_at)}.</>}</p>
  </>
}
