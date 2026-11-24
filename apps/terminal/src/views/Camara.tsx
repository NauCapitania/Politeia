import { useMemo, useState } from 'react'
import { Button, HTMLSelect, InputGroup, NonIdealState, Spinner, Tab, Tabs } from '@blueprintjs/core'
import { useInstitutions } from '../api/client'
import {
  CAMARA, useCamaraCommittee, useCamaraCommittees, useCamaraComposition, useCamaraSwitches, useCamaraVote, useCamaraVotes,
} from '../api/camara'
import { fmtDate, partyColor } from '../format'
import { useStore } from '../store'
import { Hemicycle } from './Hemicycle'
import { Proposals } from './Proposals'
import './camara.css'

type CamaraTab = 'composicao' | 'trocas' | 'votacoes' | 'proposicoes' | 'comissoes'
const SYNC = (scope: string) => `Execute \`python -m engine.cli sync --institution ${CAMARA} --scope ${scope}\`.`

export function Camara() {
  const [tab, setTab] = useState<CamaraTab>('composicao')
  return (
    <div className="view">
      <h1>Câmara dos Deputados</h1>
      <p className="lede">513 deputados federais eleitos pelo sistema proporcional em cada UF, para mandatos de quatro anos. A Câmara inicia a maior parte dos projetos de lei, autoriza a abertura de processo contra o presidente da República e faz a tomada de contas do presidente quando elas não são apresentadas no prazo (CF, art. 51). Dados oficiais da API de Dados Abertos da Câmara.</p>
      <Tabs id="camara-tabs" selectedTabId={tab} onChange={(t) => setTab(t as CamaraTab)} renderActiveTabPanelOnly>
        <Tab id="composicao" title="Composição" panel={<Composicao />} />
        <Tab id="trocas" title="Trocas de partido" panel={<Trocas />} />
        <Tab id="votacoes" title="Votações" panel={<Votacoes />} />
        <Tab id="proposicoes" title="Proposições" panel={<Proposicoes />} />
        <Tab id="comissoes" title="Comissões" panel={<Comissoes />} />
      </Tabs>
    </div>
  )
}

function Composicao() {
  const comp = useCamaraComposition()
  const [uf, setUf] = useState('')
  const { select } = useStore()
  const occupied = useMemo(() => (comp.data?.seats ?? []).filter((s) => s.state === 'occupied'), [comp.data])
  const ufs = useMemo(() => {
    const m = new Map<string, Map<string, number>>()
    occupied.forEach((s) => {
      const u = s.represented_unit ?? '?'
      const row = m.get(u) ?? new Map<string, number>()
      row.set(s.party_abbreviation ?? 's/ partido', (row.get(s.party_abbreviation ?? 's/ partido') ?? 0) + 1)
      m.set(u, row)
    })
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [occupied])
  if (comp.isLoading) return <Spinner size={24} />
  if (!comp.data || !occupied.length) return <NonIdealState icon="people" title="Deputados ainda não ingeridos" description={SYNC('members')} />
  const total = comp.data.observed_members
  const maxUf = Math.max(...ufs.map(([, row]) => [...row.values()].reduce((a, b) => a + b, 0)))
  return (
    <div>
      {comp.data.discrepancy && <p className="small muted">{comp.data.discrepancy === `${total} members observed in source for 513 official seats` ? `${total} deputados em exercício observados para 513 cadeiras.` : comp.data.discrepancy}</p>}
      <div className="split">
        <div className="card">
          <Hemicycle comp={comp.data} width={720} />
          <h3>Bancadas</h3>
          <div className="camara-bars">
            {comp.data.groups.map((g) => (
              <div key={g.party?.id ?? 'none'} className="camara-bar-row">
                <span className="mono camara-label">{g.party?.abbreviation ?? 's/ partido'}</span>
                <span className="camara-track"><span className="camara-bar" style={{ width: `${(g.count / comp.data!.groups[0].count) * 100}%`, background: partyColor(g.party?.abbreviation) }} /></span>
                <span className="mono faint">{g.count} · {((g.count / total) * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3>Bancadas por UF</h3>
          <p className="small muted">Cada UF elege de 8 a 70 deputados, proporcionalmente à população. Clique para listar.</p>
          {ufs.map(([u, row]) => {
            const n = [...row.values()].reduce((a, b) => a + b, 0)
            return (
              <button key={u} className={`list-row ${uf === u ? 'active' : ''}`} onClick={() => setUf(uf === u ? '' : u)}>
                <b className="mono camara-label" style={{ width: 28 }}>{u}</b>
                <span className="camara-track">
                  <span className="camara-stack" style={{ width: `${(n / maxUf) * 100}%` }}>
                    {[...row.entries()].sort((a, b) => b[1] - a[1]).map(([p, c]) => (
                      <i key={p} title={`${p}: ${c}`} style={{ flex: c, background: partyColor(p) }} />
                    ))}
                  </span>
                </span>
                <span className="faint mono">{n}</span>
              </button>
            )
          })}
          {uf && (
            <div className="member-grid" style={{ marginTop: 8 }}>
              {occupied.filter((s) => s.represented_unit === uf).map((s) => (
                <button key={s.mandate_id} className="member-chip" onClick={() => s.person_id && select(s.person_id)}>
                  <i style={{ background: partyColor(s.party_abbreviation) }} />
                  <span className="grow">{s.name}</span>
                  <span className="faint mono">{s.party_abbreviation}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Trocas() {
  const list = useCamaraSwitches()
  const { select } = useStore()
  const flows = useMemo(() => {
    const m = new Map<string, number>()
    ;(list.data ?? []).forEach((t) => m.set(`${t.from}→${t.to}`, (m.get(`${t.from}→${t.to}`) ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15)
  }, [list.data])
  const balance = useMemo(() => {
    const m = new Map<string, number>()
    ;(list.data ?? []).forEach((t) => { m.set(t.to, (m.get(t.to) ?? 0) + 1); m.set(t.from, (m.get(t.from) ?? 0) - 1) })
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [list.data])
  if (list.isLoading) return <Spinner size={24} />
  if (!list.data?.length) return <NonIdealState icon="swap-horizontal" title="Nenhuma troca de partido registrada" description={SYNC('members')} />
  const maxAbs = Math.max(...balance.map(([, n]) => Math.abs(n)), 1)
  return (
    <div>
      <p className="lede">{list.data.length} trocas de partido desde 1º/02/2023, segundo o histórico de cada deputado na Câmara (inclui fusões e incorporações de partidos; não é a filiação oficial do TSE).</p>
      <div className="split">
        <div className="card">
          <h3>Saldo por partido</h3>
          {balance.map(([p, n]) => (
            <div key={p} className="camara-bar-row">
              <span className="mono camara-label">{p}</span>
              <span className="camara-diverge">
                <i style={{ width: `${(Math.abs(n) / maxAbs) * 50}%`, background: partyColor(p), [n < 0 ? 'right' : 'left']: '50%' }} />
              </span>
              <span className={`mono ${n < 0 ? 'faint' : ''}`}>{n > 0 ? `+${n}` : n}</span>
            </div>
          ))}
          <h3>Fluxos mais comuns</h3>
          {flows.map(([k, n]) => <div key={k} className="small"><span className="mono">{k}</span> <span className="faint">{n}</span></div>)}
        </div>
        <div className="card list">
          {list.data.map((t, i) => (
            <button key={`${t.person_id}-${i}`} className="list-row" onClick={() => select(t.person_id)}>
              <span className="mono">{fmtDate(t.date)}</span>
              <span className="grow">{t.name}</span>
              <span className="party-pill" style={{ background: partyColor(t.from) }}>{t.from}</span>→
              <span className="party-pill" style={{ background: partyColor(t.to) }}>{t.to}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const PAGE = 200
const COLOR: Record<string, string> = { Sim: '#3fb68b', Não: '#e5534b', Abstenção: '#d9a400', Obstrução: '#8a63d2' }
const TOTAL_LABEL: Record<string, string> = { totalVotosSim: 'Sim', totalVotosNao: 'Não', totalVotosAbstencao: 'Abstenção', totalVotosObstrucao: 'Obstrução' }

function Votacoes() {
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('true')
  const [limit, setLimit] = useState(PAGE)
  const [open, setOpen] = useState<string | null>(null)
  const list = useCamaraVotes(q, kind === '' ? undefined : kind === 'true', limit)
  const vote = useCamaraVote(open)
  const { select } = useStore()
  const byParty = useMemo(() => {
    const m = new Map<string, Record<string, number>>()
    vote.data?.votes.forEach((v) => {
      const row = m.get(v.party ?? '?') ?? {}
      row[v.vote ?? '?'] = (row[v.vote ?? '?'] ?? 0) + 1
      m.set(v.party ?? '?', row)
    })
    return [...m.entries()].sort((a, b) => Object.values(b[1]).reduce((x, y) => x + y, 0) - Object.values(a[1]).reduce((x, y) => x + y, 0))
  }, [vote.data])
  return (
    <div>
      <p className="lede">Votações do Plenário publicadas nos Dados Abertos da Câmara. Só as votações nominais (painel eletrônico) trazem o voto de cada deputado; as simbólicas registram apenas o resultado.</p>
      <div className="toolbar">
        <InputGroup leftIcon="search" placeholder="Filtrar por descrição ou proposição" value={q} onValueChange={(v) => { setQ(v); setLimit(PAGE) }} small />
        <HTMLSelect minimal value={kind} onChange={(e) => { setKind(e.currentTarget.value); setLimit(PAGE) }}
          options={[{ value: 'true', label: 'Nominais' }, { value: 'false', label: 'Simbólicas' }, { value: '', label: 'Todas' }]} />
      </div>
      <div className="split">
        <div className="list">
          {list.isLoading && <Spinner size={20} />}
          {list.data && !list.data.length && <NonIdealState icon="th-list" title="Nenhuma votação" description={SYNC('votes')} />}
          {list.data?.map((v) => (
            <button key={v.id} className={`list-row ${open === v.id ? 'active' : ''}`} onClick={() => v.nominal && setOpen(v.id)}>
              <span className="mono">{fmtDate(v.date)}</span>
              <span className="grow">{v.matter && <b>{v.matter} · </b>}{v.description}</span>
              {!v.nominal && <span className="kind kind-analysis">simbólica</span>}
              <span className="small muted">{v.result}</span>
            </button>
          ))}
          {list.data && list.data.length >= limit && (
            <Button minimal small icon="more" onClick={() => setLimit(limit + PAGE)}>Mostrar votações mais antigas</Button>
          )}
        </div>
        <div className="card">
          {!open && <p className="muted">Selecione uma votação nominal para ver como cada bancada e cada deputado votou.</p>}
          {vote.data && (
            <>
              <h3>{vote.data.matter ?? 'Votação'} — {fmtDate(vote.data.date)}</h3>
              <p>{vote.data.description}</p>
              <p className="small">Resultado: <b>{vote.data.result ?? '—'}</b> · {Object.entries(vote.data.totals ?? {}).map(([k, n]) => `${TOTAL_LABEL[k] ?? k}: ${n}`).join(' · ')}</p>
              <h3>Por bancada</h3>
              {byParty.map(([p, row]) => {
                const n = Object.values(row).reduce((a, b) => a + b, 0)
                return (
                  <div key={p} className="camara-bar-row">
                    <span className="mono camara-label">{p}</span>
                    <span className="camara-track">
                      <span className="camara-stack" style={{ width: '100%' }}>
                        {Object.entries(row).map(([k, c]) => <i key={k} title={`${k}: ${c}`} style={{ flex: c, background: COLOR[k] ?? 'var(--line-strong)' }} />)}
                      </span>
                    </span>
                    <span className="faint mono">{n}</span>
                  </div>
                )
              })}
              <h3>Votos individuais</h3>
              <div className="vote-grid">
                {vote.data.votes.map((v) => (
                  <button key={v.person_id} className="vote-chip" onClick={() => select(v.person_id)} title={v.label ?? undefined}
                    style={{ borderColor: COLOR[v.vote ?? ''] ?? 'var(--line-strong)' }}>
                    <i style={{ background: partyColor(v.party) }} />{v.name} <span className="muted">{v.party}-{v.uf}</span> <b style={{ color: COLOR[v.vote ?? ''] }}>{v.vote}</b>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Proposicoes() {
  const insts = useInstitutions()
  const inst = insts.data?.find((i) => i.id === CAMARA)
  if (insts.isLoading) return <Spinner size={24} />
  if (!inst) return <NonIdealState icon="document" title="Câmara não cadastrada" description="Execute `python -m engine.cli bootstrap`." />
  return <Proposals inst={inst} />
}

const ROLE: Record<string, string> = { PRESIDENTE: 'Presidente', 'VICE-PRESIDENTE': 'Vice-presidente' }

function Comissoes() {
  const list = useCamaraCommittees()
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState<string | null>(null)
  const rows = useMemo(() => (list.data ?? []).filter((c) => !q || `${c.abbreviation} ${c.name}`.toLowerCase().includes(q.toLowerCase())), [list.data, q])
  const current = focus ?? list.data?.find((c) => c.abbreviation === 'CCJC')?.id ?? list.data?.[0]?.id
  const detail = useCamaraCommittee(current)
  const { select } = useStore()
  if (list.isLoading) return <Spinner size={24} />
  if (!list.data?.length) return <NonIdealState icon="people" title="Comissões ainda não ingeridas" description={SYNC('committees')} />
  const d = detail.data
  const by = (k: string) => (d?.members ?? []).filter((m) => m.seat_kind === k)
  return (
    <div>
      <p className="lede">As comissões permanentes analisam as proposições por tema antes do Plenário e, em muitos projetos, decidem em caráter conclusivo. CPIs investigam fatos determinados com poderes de autoridade judicial.</p>
      <div className="committees">
        <div className="committee-list">
          <InputGroup small leftIcon="search" placeholder="Filtrar comissões…" value={q} onValueChange={setQ} />
          {rows.map((c) => (
            <button key={c.id} className={`list-row ${c.id === current ? 'active' : ''}`} onClick={() => setFocus(c.id)}>
              <b className="mono">{c.abbreviation}</b>
              <span className="grow">{c.subtitle ?? c.name}</span>
              <span className="faint mono">{c.titulares}</span>
            </button>
          ))}
        </div>
        <div className="card">
          {detail.isLoading && <Spinner size={20} />}
          {d && (
            <>
              <h2>{d.abbreviation} — {d.name}</h2>
              <div className="facts">
                {d.members.filter((m) => m.role).map((m) => (
                  <span key={m.person_id}><span className="faint">{ROLE[m.role!] ?? m.role}</span> <a className="link" onClick={() => select(m.person_id)}>{m.name}</a> ({m.party}-{m.uf})</span>
                ))}
                {d.attributes?.room && <span><span className="faint">Sala</span> {d.attributes.room}</span>}
                {d.attributes?.url && <a className="link" href={d.attributes.url} target="_blank" rel="noreferrer">Página oficial ↗</a>}
              </div>
              {(['titular', 'suplente'] as const).map((k) => (
                <div key={k}>
                  <h3>{k === 'titular' ? 'Titulares' : 'Suplentes'} ({by(k).length})</h3>
                  <div className="member-grid">
                    {by(k).map((m) => (
                      <button key={m.person_id} className="member-chip" onClick={() => select(m.person_id)}>
                        <i style={{ background: partyColor(m.party) }} />
                        <span className="grow">{m.name}</span>
                        <span className="faint mono">{m.party}-{m.uf}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              <p className="faint" style={{ marginTop: 12 }}>Composição observada em {fmtDate(d.last_observed_at)} · Dados Abertos da Câmara</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
