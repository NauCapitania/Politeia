import { useState } from 'react'
import { Button, HTMLSelect, InputGroup, Spinner } from '@blueprintjs/core'
import { useVote, useVotes } from '../api/client'
import { fmtDate, partyColor } from '../format'
import { useStore } from '../store'

const PAGE = 200
const COLOR: Record<string, string> = { Sim: '#3fb68b', Não: '#e5534b', Abstenção: '#d9a400' }

export function Votacoes() {
  const [q, setQ] = useState('')
  const [secreta, setSecreta] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [limit, setLimit] = useState(PAGE)
  const list = useVotes(q, secreta, limit)
  const vote = useVote(open)
  const { select } = useStore()
  return (
    <div className="view">
      <h1>Votações nominais no plenário</h1>
      <p className="lede">Votações publicadas pelos Dados Abertos do Senado desde 2025. Em votações secretas o Senado publica só quem votou, não o voto.</p>
      <div className="toolbar">
        <InputGroup leftIcon="search" placeholder="Filtrar por descrição ou matéria" value={q} onValueChange={(v) => { setQ(v); setLimit(PAGE) }} small />
        <HTMLSelect minimal value={secreta} onChange={(e) => { setSecreta(e.currentTarget.value); setLimit(PAGE) }}
          options={[{ value: '', label: 'Todas' }, { value: 'false', label: 'Abertas' }, { value: 'true', label: 'Secretas' }]} />
      </div>
      <div className="split">
        <div className="list">
          {list.isLoading && <Spinner size={20} />}
          {list.data?.map((v) => (
            <button key={v.id} className={`list-row ${open === v.id ? 'active' : ''}`} onClick={() => setOpen(v.id)}>
              <span className="mono">{fmtDate(v.date)}</span>
              <span className="grow">{v.matter && <b>{v.matter} · </b>}{v.description}</span>
              {v.secret && <span className="kind kind-analysis">secreta</span>}
              <span className="small muted">{v.result}</span>
            </button>
          ))}
          {list.data && list.data.length >= limit && (
            <Button minimal small icon="more" loading={list.isFetching} onClick={() => setLimit(limit + PAGE)}>Mostrar votações mais antigas</Button>
          )}
        </div>
        <div className="card">
          {!open && <p className="muted">Selecione uma votação para ver os votos individuais.</p>}
          {vote.data && (
            <>
              <h3>{vote.data.matter ?? 'Votação'} — {fmtDate(vote.data.date)}</h3>
              <p>{vote.data.description}</p>
              <p className="small">Resultado: <b>{vote.data.result ?? '—'}</b> · {Object.entries(vote.data.totals ?? {}).map(([k, n]) => `${k}: ${n}`).join(' · ')}</p>
              <div className="vote-grid">
                {vote.data.votes.map((v: any) => (
                  <button key={v.person_id} className="vote-chip" onClick={() => select(v.person_id)} title={v.label}
                    style={{ borderColor: COLOR[v.vote] ?? 'var(--line-strong)' }}>
                    <i style={{ background: partyColor(v.party) }} />{v.name} <span className="muted">{v.party}-{v.uf}</span> <b style={{ color: COLOR[v.vote] }}>{v.vote}</b>
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
