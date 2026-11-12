import { useState } from 'react'
import { Button, Collapse } from '@blueprintjs/core'
import { useSource, type SourceRef } from '../api/client'
import { fmtDateTime } from '../format'

export function SourceLink({ source }: { source: SourceRef }) {
  const [open, setOpen] = useState(false)
  const rec = useSource(open ? source : null)
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span className="chip mono">{source.record_kind}</span>
        <span className="faint mono">{fmtDateTime(source.retrieved_at)}</span>
        <Button size="small" variant="minimal" icon={open ? 'chevron-up' : 'code'} onClick={() => setOpen(!open)} aria-label="Ver registro de origem" />
      </div>
      <a className="link mono" href={source.url} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all' }}>{source.url}</a>
      <Collapse isOpen={open}>
        <div className="faint mono" style={{ marginTop: 6 }}>
          {source.json_path} · sha256 {source.content_sha256.slice(0, 12)}…
        </div>
        {rec.data && (
          <pre className="excerpt">
            {typeof rec.data.excerpt === 'string' ? rec.data.excerpt : JSON.stringify(rec.data.excerpt, null, 2) ?? 'Trecho indisponível'}
          </pre>
        )}
      </Collapse>
    </div>
  )
}
