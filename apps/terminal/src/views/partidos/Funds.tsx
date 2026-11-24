import { useState } from 'react'
import { SrcList } from '../../components/SrcList'
import { compactMoney, fundNames, money, share, type Comparison, type Fund, type Funding, type Party } from './data'

function Bars({ rows, total, maxRows }: {
  rows: { id: string; label: string; cents: number }[]
  total: number
  maxRows?: number
}) {
  const max = Math.max(1, ...rows.map(row => row.cents))
  return <ol className="partidos-bar-list">{rows.slice(0, maxRows ?? rows.length).map(row =>
    <li key={row.id} title={money(row.cents)}>
      <span>{row.label}</span>
      <span className="partidos-bar-track" aria-hidden="true"><i style={{ width: `${row.cents / max * 100}%` }} /></span>
      <b>{compactMoney(row.cents)}</b><small>{share(row.cents, total)}</small>
    </li>)}</ol>
}

function FusionComparison({ entry, funding, names }: { entry: Comparison; funding: Funding[]; names: Map<string, string> }) {
  const observations = [entry.before, entry.after].flatMap(side => {
    const period = funding.find(row => row.fund === entry.fund && row.year === side.year)
    if (!period) return []
    const keys = new Set(side.partyIds)
    const rows = period.allocations.filter(row => keys.has(row.partyId))
    const cents = rows.reduce((sum, row) => sum + row.cents, 0)
    return [{ year: side.year, cents, total: period.totalCents, rows }]
  })
  if (observations.length !== 2) return null
  const scale = Math.max(...observations.map(row => row.cents / row.total))
  return <article className="partidos-panel partidos-comparison">
    <p className="partidos-kicker">Comparação · análise</p>
    <h2>{entry.title}</h2>
    <div className="partidos-compare-grid">
      {observations.map((row, i) => <div key={row.year}>
        <span>{i === 0 ? 'Antes da fusão' : 'Depois da fusão'} · {row.year}</span>
        <strong>{share(row.cents, row.total)} do FEFC</strong>
        <div className="partidos-bar-track" aria-hidden="true">
          <i style={{ width: `${row.cents / row.total / scale * 100}%` }} />
        </div>
        <p>{money(row.cents)}</p>
        <ul>{row.rows.map(allocation =>
          <li key={allocation.partyId}>{names.get(allocation.partyId)}: {money(allocation.cents)}</li>)}</ul>
      </div>)}
    </div>
    <p>{entry.text}</p>
    <SrcList sources={entry.sources} />
  </article>
}

export function Funds({ funding, parties, comparisons }: { funding: Funding[]; parties: Party[]; comparisons: Comparison[] }) {
  const [fund, setFund] = useState<Fund>('fefc')
  const [year, setYear] = useState<number>()
  const [expanded, setExpanded] = useState(false)
  const names = new Map(parties.map(party => [party.partyId, party.abbreviation]))
  const periods = funding.filter(row => row.fund === fund).sort((a, b) => a.year - b.year)
  const active = periods.find(row => row.year === year) ?? periods.at(-1)
  if (!active) return <p>Nenhum valor disponível para este fundo.</p>
  const max = Math.max(...periods.map(row => row.totalCents))
  const rows = [...active.allocations].sort((a, b) => b.cents - a.cents).map(row =>
    ({ id: row.partyId, label: names.get(row.partyId) ?? row.partyId, cents: row.cents }))
  return <div className="partidos-stack">
    <section className="partidos-panel">
      <div className="partidos-heading">
        <div><h2>Distribuição dos fundos públicos</h2><p>Valores nominais, sem correção pela inflação.</p></div>
        <div className="partidos-selects"><label>Fundo <select value={fund} onChange={e => {
          setFund(e.target.value as Fund); setYear(undefined); setExpanded(false)
        }}>
          {Object.entries(fundNames).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select></label></div>
      </div>
      <div className="partidos-fund-grid">
        <section aria-label="Série histórica">
          <h3>Total por {fund === 'fefc' ? 'eleição' : 'exercício'}</h3>
          <div className="partidos-series">
            {periods.map(row => <button key={row.year} type="button" aria-pressed={row.year === active.year}
              aria-label={`${row.year}${row.partial ? ' parcial' : ''}: ${money(row.totalCents)}`}
              onClick={() => { setYear(row.year); setExpanded(false) }}>
              <span>{row.year}{row.partial ? '*' : ''}</span>
              <span className={`partidos-bar-track${row.partial ? ' is-partial' : ''}`} aria-hidden="true">
                <i style={{ width: `${row.totalCents / max * 100}%` }} />
              </span><b>{compactMoney(row.totalCents)}</b>
            </button>)}
          </div>
          {periods.some(row => row.partial) && <p className="partidos-note">* Período parcial; não compare diretamente a anos completos.</p>}
        </section>
        <section aria-label="Distribuição por legenda">
          <h3>{active.year} {active.partial ? '· parcial' : ''} · {money(active.totalCents)}</h3>
          {rows.length > 0 ? <>
            <p className="partidos-note">Valor e participação no total do período. As barras usam a maior cota como escala.</p>
            <Bars rows={rows} total={active.totalCents} maxRows={expanded ? undefined : 8} />
            {rows.length > 8 && <button className="partidos-text-button" type="button" onClick={() => setExpanded(!expanded)}>
              {expanded ? 'Mostrar as 8 maiores' : `Mostrar todas as ${rows.length} legendas`}
            </button>}
          </> : <p>Distribuição por legenda não incluída neste recorte.</p>}
          {active.budgetCents != null && active.finesCents != null && <p className="partidos-note">
            Dotação distribuída: {money(active.budgetCents)} · Multas distribuídas: {money(active.finesCents)}.
          </p>}
          <p className="partidos-note">{active.note}</p>
          <SrcList sources={active.sources} />
        </section>
      </div>
    </section>
    {comparisons.filter(entry => entry.fund === fund).map(entry =>
      <FusionComparison key={entry.id} entry={entry} funding={funding} names={names} />)}
  </div>
}
