import { useState } from 'react'
import { Spinner, Tag } from '@blueprintjs/core'
import { useNews } from '../api/client'
import { fmtDateTime } from '../format'
import { useStore } from '../store'

const TEMAS: [string, string][] = [['', 'Tudo'], ['impeachment_stf', 'Impeachment'], ['pgr', 'PGR'], ['stf', 'STF'], ['caso_master', 'Caso Master'], ['presidencia_senado', 'Presidência do Senado'], ['senado', 'Senado']]

export function Noticias() {
  const [tema, setTema] = useState('')
  const news = useNews(tema || undefined)
  const { select } = useStore()
  return (
    <div className="view">
      <h1>Notícias</h1>
      <p className="lede">Manchetes de feeds RSS públicos (Agência Senado, g1, Folha, Estadão, Poder360 e outros). O Politeia guarda só título, link, data e um trecho curto; o texto fica no veículo. Senadores e ministros são ligados apenas quando o nome completo aparece.</p>
      <div className="toolbar">{TEMAS.map(([k, l]) => <Tag key={k} interactive minimal={tema !== k} intent={tema === k ? 'primary' : 'none'} onClick={() => setTema(k)}>{l}</Tag>)}</div>
      {news.isLoading && <Spinner size={20} />}
      <div className="news-list">
        {news.data?.map((n) => (
          <article key={n.id} className="news-item">
            <a className="link title" href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
            <div className="small muted">{n.outlet} · {fmtDateTime(n.published_at)}</div>
            {n.excerpt && <p className="small">{n.excerpt}</p>}
            <div>
              {n.mentions.map((m: any) => (
                <Tag key={m.id} minimal interactive={m.kind === 'person'} onClick={() => m.kind === 'person' && select(m.id)}>{m.text}</Tag>
              ))}
            </div>
          </article>
        ))}
        {news.data && !news.data.length && <p className="muted">Nenhuma notícia neste tema.</p>}
      </div>
    </div>
  )
}
