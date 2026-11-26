import type { Src } from '../api/client'

const KIND: Record<string, string> = { official: 'Oficial', press_report: 'Imprensa', declaration: 'Declaração', analysis: 'Análise' }

function pageLabel(url: string) {
  const { host, pathname, search, hash } = new URL(url)
  return `${host}${pathname}${search}${hash}`
}

export function SrcList({ sources, showPage = false, hidePress = false }: { sources?: Src[]; showPage?: boolean; hidePress?: boolean }) {
  const visible = hidePress ? sources?.filter((source) => source.kind !== 'press_report') : sources
  if (!visible?.length) return null
  return (
    <span className="src-list">
      {visible.map((s, i) => (
        <a key={i} className={showPage ? 'src-chip src-chip-page' : 'src-chip'} href={s.url} target="_blank" rel="noreferrer" title={s.url}>
          <span className={`kind kind-${s.kind}`}>{KIND[s.kind] ?? s.kind}</span>
          {s.outlet}{showPage ? ` · ${pageLabel(s.url)}` : ''}{s.date ? ` · ${s.date.split('-').reverse().join('/')}` : ''}
        </a>
      ))}
    </span>
  )
}

export function Badge({ kind }: { kind: string }) {
  return <span className={`kind kind-${kind}`}>{KIND[kind] ?? kind}</span>
}
