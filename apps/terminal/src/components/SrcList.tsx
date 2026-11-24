import type { Src } from '../api/client'

const KIND: Record<string, string> = { official: 'Oficial', press_report: 'Imprensa', declaration: 'Declaração', analysis: 'Análise' }

export function SrcList({ sources }: { sources?: Src[] }) {
  if (!sources?.length) return null
  return (
    <span className="src-list">
      {sources.map((s, i) => (
        <a key={i} className="src-chip" href={s.url} target="_blank" rel="noreferrer" title={s.url}>
          <span className={`kind kind-${s.kind}`}>{KIND[s.kind] ?? s.kind}</span>
          {s.outlet}{s.date ? ` · ${s.date.split('-').reverse().join('/')}` : ''}
        </a>
      ))}
    </span>
  )
}

export function Badge({ kind }: { kind: string }) {
  return <span className={`kind kind-${kind}`}>{KIND[kind] ?? kind}</span>
}
