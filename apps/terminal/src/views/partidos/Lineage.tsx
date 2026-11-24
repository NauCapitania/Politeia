import { useMemo, useState } from 'react'
import { SrcList } from '../../components/SrcList'
import { dateLabel, eventTypes, type LineageEvent, type Party } from './data'

const firstYear = 1964
const lane = 35
const xStart = 154
const touches = (e: LineageEvent, id: string) => e.from.includes(id) || e.to.includes(id)
const isEdge = (e: LineageEvent) => e.from.length > 0 && e.to.length > 0 && e.type !== 'contexto'
const ends = (e: LineageEvent) => ['fusao', 'incorporacao', 'renomeacao', 'extincao'].includes(e.type)
const activates = (e: LineageEvent) => e.type !== 'contexto' && e.type !== 'registro'

function family(focus: string, events: LineageEvent[]) {
  const related = new Set([focus])
  function visit(id: string, direction: 'from' | 'to', seen: Set<string>) {
    if (seen.has(id)) return
    seen.add(id)
    for (const e of events.filter(isEdge)) {
      if (!e[direction].includes(id)) continue
      for (const parent of e[direction === 'from' ? 'to' : 'from']) {
        related.add(parent)
        visit(parent, direction, seen)
      }
    }
  }
  visit(focus, 'from', new Set())
  visit(focus, 'to', new Set())
  return related
}

function yearOf(date: string) {
  const [year, month = 1, day = 1] = date.split('-').map(Number)
  return year + ((month - 1) * 31 + day - 1) / 372
}

export function Lineage({ parties, events, asOf }: { parties: Party[]; events: LineageEvent[]; asOf: string }) {
  const preferred = 'uniao'
  const [focus, setFocus] = useState(parties.some(p => p.partyId === preferred) ? preferred : '')
  const [type, setType] = useState('')
  const [selectedId, setSelectedId] = useState('partidos-fusao-uniao')
  const byId = useMemo(() => new Map(parties.map(p => [p.partyId, p])), [parties])
  const chronology = useMemo(() => [...events].sort((a, b) =>
    a.date.localeCompare(b.date) || Number(a.type === 'registro') - Number(b.type === 'registro')), [events])
  const related = focus ? family(focus, chronology) : new Set(byId.keys())
  const visibleEvents = chronology.filter(e => {
    const inFamily = isEdge(e)
      ? e.from.some(id => related.has(id)) && e.to.some(id => related.has(id))
      : [...e.from, ...e.to].some(id => related.has(id))
    return (!focus || inFamily) && (!type || e.type === type)
  })
  const visibleIds = new Set([...related, ...visibleEvents.flatMap(e => [...e.from, ...e.to])])
  const selected = visibleEvents.find(e => e.id === selectedId) ?? visibleEvents.at(-1)
  const cssKind = (event: LineageEvent) => `partidos-kind-${event.type}`
  const endYear = Number(asOf.slice(0, 4)) + 1
  const selectedParty = byId.get(focus)
  const rows = [...visibleIds].map(id => {
    const record = chronology.filter(e => touches(e, id))
    const start = record.find(e => e.to.includes(id) && activates(e)) ?? record[0]
    const observed = record[0]
    const end = record.find(e => e.from.includes(id) && ends(e))
    return { id, start: start ? Math.min(yearOf(start.date), yearOf(observed.date)) : undefined, end: end && yearOf(end.date) }
  }).sort((a, b) => (a.start ?? endYear) - (b.start ?? endYear) ||
    a.id.localeCompare(b.id))
  const yOf = new Map(rows.map((row, i) => [row.id, (i + 1) * lane + 10]))
  const xOf = (year: number) => xStart + (year - firstYear) * 12.5
  const width = xOf(endYear) + 24
  const height = Math.max(100, (rows.length + 1) * lane + 10)
  const ticks = [1964, 1970, 1980, 1990, 2000, 2010, 2020, endYear - 1].filter((year, i, years) =>
    year < endYear && years.indexOf(year) === i)

  return (
    <div className="partidos-stack">
      <section className="partidos-panel">
        <div className="partidos-heading">
          <div><h2>Árvore partidária</h2><p>{selectedParty ? `Origens e desdobramentos de ${selectedParty.name}` : 'Todas as linhagens do recorte'}</p></div>
          <div className="partidos-selects">
            <label>Sigla <select value={focus} onChange={e => setFocus(e.target.value)}>
              <option value="">Todas as siglas</option>
              {[...parties].sort((a, b) => a.abbreviation.localeCompare(b.abbreviation, 'pt-BR')).map(p =>
                <option key={p.partyId} value={p.partyId}>{p.abbreviation}</option>)}
            </select></label>
            <label>Evento <select value={type} onChange={e => setType(e.target.value)}>
              <option value="">Todos os eventos</option>
              {Object.entries(eventTypes).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select></label>
          </div>
        </div>
        <div className="partidos-legend" aria-label="Legenda">
          {Object.entries(eventTypes).map(([id, name]) => <span className={`partidos-kind-${id}`} key={id}><i />{name}</span>)}
        </div>
        <div className="partidos-graph" tabIndex={0} role="region" aria-label="Gráfico de linhagem partidária">
          <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-label="Siglas e relações no tempo">
            {ticks.map(year => <g className="partidos-grid" key={year}>
              <line x1={xOf(year)} x2={xOf(year)} y1="29" y2={height - 9} />
              <text x={xOf(year)} y="20" textAnchor="middle">{year}</text>
            </g>)}
            {rows.map(row => {
              const y = yOf.get(row.id)!
              return <g key={row.id}>
                {row.start !== undefined && <line className="partidos-lane" x1={xOf(row.start)} x2={xOf(Math.max(row.start, row.end ?? endYear))} y1={y} y2={y} />}
                <text className="partidos-svg-button" role="button" tabIndex={0} x="12" y={y + 4}
                  aria-label={`Explorar ${byId.get(row.id)?.name}`} aria-pressed={focus === row.id}
                  onClick={() => setFocus(row.id)} onKeyDown={e => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFocus(row.id) }
                  }}>{byId.get(row.id)?.abbreviation}</text>
              </g>
            })}
            {visibleEvents.filter(isEdge).map(event => {
              const x = xOf(yearOf(event.date))
              const ys = [...event.from, ...event.to].map(id => yOf.get(id)!)
              return <line key={event.id} className={`partidos-edge ${cssKind(event)}`} x1={x} x2={x}
                y1={Math.min(...ys)} y2={Math.max(...ys)} />
            })}
            {visibleEvents.map(event => {
              const y = yOf.get(event.to[0] ?? event.from[0]) ?? 30
              const x = xOf(yearOf(event.date)) + (event.type === 'registro' ? 5 : 0)
              const active = selected?.id === event.id
              return <g key={event.id} className={`partidos-svg-button partidos-point ${cssKind(event)}`} role="button"
                aria-label={event.title} aria-pressed={active} tabIndex={0}
                onClick={() => setSelectedId(event.id)} onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(event.id) }
                }}>
                <title>{event.title} · {dateLabel(event.date)}</title>
                <circle cx={x} cy={y} r={active ? 8 : 5} />
              </g>
            })}
          </svg>
        </div>
        <p className="partidos-note">Selecione uma sigla ou um marco. A posição mostra a data documentada; as linhas horizontais não certificam o período completo de atividade.</p>
      </section>
      <section className="partidos-panel partidos-event-grid" aria-label="Cronologia e evidências">
        <div>
          <h2>Cronologia <small>{visibleEvents.length} marcos</small></h2>
          <div className="partidos-event-list">
            {[...visibleEvents].reverse().map(event => <button key={event.id} type="button"
              className={cssKind(event)} aria-pressed={selected?.id === event.id} onClick={() => setSelectedId(event.id)}>
              <time dateTime={event.date}>{dateLabel(event.date)}</time><span>{event.title}</span>
            </button>)}
          </div>
        </div>
        <div className="partidos-event-detail" aria-live="polite">
          {selected ? <>
            <div className={`partidos-event-tag ${cssKind(selected)}`}>{eventTypes[selected.type]} · {dateLabel(selected.date)}</div>
            <h3>{selected.title}</h3>
            <p>{selected.summary}</p>
            {selected.from.length > 0 && <p><b>Origem:</b> {selected.from.map(id => byId.get(id)?.abbreviation).join(' + ')}</p>}
            {selected.to.length > 0 && <p><b>Destino:</b> {selected.to.map(id => byId.get(id)?.abbreviation).join(' + ')}</p>}
            <p><b>Pessoas documentadas:</b> {selected.people?.join(', ') ?? 'Não identificadas neste recorte.'}</p>
            <p><b>Motivo declarado:</b> {selected.declared ?? 'Não documentado nas fontes deste marco.'}</p>
            {selected.analysis && <p><b>Análise, não declaração:</b> {selected.analysis}</p>}
            <SrcList sources={selected.sources} />
          </> : <p>Nenhum marco para esta combinação de filtros.</p>}
        </div>
      </section>
    </div>
  )
}
