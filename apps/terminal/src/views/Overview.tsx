import { Button, Icon, Spinner } from '@blueprintjs/core'
import { useChanges, useNews, type Institution } from '../api/client'
import { useCurrentSeats } from '../useCurrentSeats'
import { fmtDate, fmtDateTime, partyColor } from '../format'
import { useStore } from '../store'

export function Overview({ inst }: { inst: Institution }) {
  const seats = useCurrentSeats()
  const news = useNews()
  const changes = useChanges()
  const { setView, setSenadoTab, select } = useStore()
  const rows = seats.data?.seats ?? []
  const parties = [...rows.reduce((m, s) => m.set(s.party ?? 'Filiação não informada', (m.get(s.party ?? 'Filiação não informada') ?? 0) + 1), new Map<string, number>())]
    .sort((a, b) => b[1] - a[1])
  const partyCount = new Set(rows.map((s) => s.party).filter(Boolean)).size
  const latest = [...(news.data ?? [])].sort((a, b) => (b.published_at ?? '').localeCompare(a.published_at ?? '')).slice(0, 4)
  const recent = [...(changes.data ?? [])].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 3)

  return <div className="view overview">
    <div className="overview-heading">
      <div><div className="eyebrow"><span className="dot ok" /> SEU RADAR INSTITUCIONAL</div><h1>A política em perspectiva.</h1>
        <p>Conecte os fatos. Acompanhe o poder. Forme sua análise.</p></div>
      <button className="quiet-button" onClick={() => setView('sources')}><Icon icon="shield" size={14} /> Verificar cobertura <Icon icon="arrow-top-right" size={12} /></button>
    </div>

    <div className="overview-metrics">
      <button className="metric" onClick={() => setSenadoTab('composicao')}><span>Senado em exercício <Icon icon="arrow-top-right" size={12} /></span><strong>{seats.isLoading ? '…' : seats.isError ? '—' : seats.data?.observed ?? '—'}<small> / {inst.seat_count ?? 81}</small></strong><em>Cadeiras identificadas na base</em></button>
      <button className="metric" onClick={() => setSenadoTab('composicao')}><span>Distribuição de poder <Icon icon="arrow-top-right" size={12} /></span><strong>{seats.isLoading ? '…' : seats.isError ? '—' : partyCount}<small> partidos</small></strong><em>Na composição consultada</em></button>
      <button className="metric" onClick={() => setView('noticias')}><span>No radar de notícias <Icon icon="arrow-top-right" size={12} /></span><strong>{news.isLoading ? '…' : news.isError ? '—' : news.data?.length ?? 0}<small> registros</small></strong><em>Últimas notícias disponíveis na base</em></button>
      <button className="metric metric-focus" onClick={() => setSenadoTab('presidencia2027')}><span>Próxima disputa <Icon icon="arrow-top-right" size={12} /></span><strong>2027<small> · Senado</small></strong><em>Cenários, apoios e incertezas</em></button>
    </div>

    <div className="overview-grid">
      <section className="workspace-card balance-card">
        <div className="workspace-card-head"><div><div className="eyebrow">01 / MAPA DO PODER</div><h2>O equilíbrio do Senado</h2></div><Icon icon="layout-circle" size={18} /></div>
        <div className="balance-visual" aria-hidden="true"><div className="orbital orbital-one" /><div className="orbital orbital-two" /><div className="orbital orbital-three" /><div className="balance-number"><b>{seats.data?.observed ?? '—'}</b><span>cadeiras observadas</span></div></div>
        {seats.isLoading && <Spinner size={18} />}
        {seats.isError && <p className="warn-text">Não foi possível carregar a composição. Consulte a cobertura das fontes.</p>}
        {!seats.isLoading && !seats.isError && !rows.length && <p className="muted">Composição ainda não disponível na base.</p>}
        <div className="power-bar" role="img" aria-label={parties.map(([p, n]) => `${p}: ${n} cadeiras`).join('; ') || 'Sem composição disponível'}>
          {parties.map(([p, n]) => <div key={p} style={{ width: `${n / rows.length * 100}%`, background: partyColor(p) }} title={`${p}: ${n}`} />)}
        </div>
        <div className="power-parties">{parties.slice(0, 6).map(([p, n]) => <span key={p}><i style={{ background: partyColor(p) }} />{p}<b>{n}</b></span>)}</div>
        <div className="card-bottom"><span>Base consultada · {fmtDate(seats.data?.date)}</span><Button minimal endIcon="arrow-right" onClick={() => setSenadoTab('composicao')}>Explorar composição</Button></div>
      </section>

      <section className="workspace-card radar-card">
        <div className="workspace-card-head"><div><div className="eyebrow">02 / RADAR DE INFORMAÇÃO</div><h2>O que está em pauta</h2></div><span className="data-badge">Na base</span></div>
        {news.isLoading && <Spinner size={20} />}
        {news.isError && <p className="warn-text">Notícias indisponíveis nesta consulta.</p>}
        {!news.isLoading && !news.isError && !latest.length && <div className="workspace-empty"><Icon icon="feed" size={28} /><p>Seu radar está pronto.</p><span>As notícias aparecerão após a coleta das fontes.</span></div>}
        <div className="radar-list">{latest.map((n, i) => <a href={n.url} target="_blank" rel="noreferrer" key={n.id} className="radar-item"><span className="radar-index">0{i + 1}</span><div><span className="news-meta">{n.outlet} · {fmtDateTime(n.published_at)}</span><h3>{n.title}</h3></div><Icon icon="arrow-top-right" size={12} /></a>)}</div>
        <div className="card-bottom"><span>Notícia não é conclusão</span><Button minimal endIcon="arrow-right" onClick={() => setView('noticias')}>Abrir notícias</Button></div>
      </section>

      <section className="workspace-card watch-card">
        <div className="workspace-card-head"><div><div className="eyebrow">03 / FRENTES DE ANÁLISE</div><h2>Acompanhe de perto</h2></div><Icon icon="locate" size={18} /></div>
        <button className="analysis-row" onClick={() => setView('stf')}><span className="analysis-icon"><Icon icon="take-action" /></span><span><b>STF e caso Master</b><small>Fatos, evidências e caminhos institucionais</small></span><Icon icon="arrow-right" size={14} /></button>
        <button className="analysis-row" onClick={() => setSenadoTab('presidencia2027')}><span className="analysis-icon amber"><Icon icon="predictive-analysis" /></span><span><b>A sucessão no Senado</b><small>Presidência de 2027 · cenários, não certezas</small></span><Icon icon="arrow-right" size={14} /></button>
        <button className="analysis-row" onClick={() => setSenadoTab('votacoes')}><span className="analysis-icon blue"><Icon icon="series-search" /></span><span><b>Como o Senado vota</b><small>Votos nominais e limites do voto secreto</small></span><Icon icon="arrow-right" size={14} /></button>
      </section>

      <section className="workspace-card movement-card">
        <div className="workspace-card-head"><div><div className="eyebrow">04 / MOVIMENTOS NA BASE</div><h2>Mudanças de composição</h2></div><Icon icon="timeline-events" size={18} /></div>
        {changes.isLoading && <Spinner size={18} />}
        {changes.isError && <p className="warn-text">Histórico indisponível nesta consulta.</p>}
        {!changes.isLoading && !changes.isError && !recent.length && <p className="muted movement-empty">Nenhuma mudança de composição registrada na base.</p>}
        {recent.map((c, i) => <button className="movement-row" key={`${c.person_id}-${c.date}-${i}`} onClick={() => { setSenadoTab('composicao'); select(c.person_id) }}><span className="movement-dot" /><div><span className="news-meta">{fmtDate(c.date)} · {c.kind === 'troca_partido' ? 'Filiação partidária' : 'Exercício de mandato'}</span><b>{c.name}</b><small>{c.detail}</small></div><Icon icon="chevron-right" size={12} /></button>)}
        <div className="method-note"><Icon icon="info-sign" size={12} />A interface se move. Os fatos só mudam com novas fontes.</div>
      </section>
    </div>
    <div className="overview-footnote"><span>POLITEIA / INTELIGÊNCIA POLÍTICA</span><span>Dados documentados. Análise com responsabilidade.</span></div>
  </div>
}
