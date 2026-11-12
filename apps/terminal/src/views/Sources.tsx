import type { Institution } from '../api/client'
import { useCapabilities, useIngestion } from '../api/client'
import { CAPABILITY_LABEL, STATUS_LABEL, fmtDateTime } from '../format'

export function Sources({ inst }: { inst: Institution }) {
  const runs = useIngestion(inst.id)
  const caps = useCapabilities(inst.id)
  return (
    <div className="view">
      <div className="view-header"><h1>Fontes e cobertura</h1><span className="sub">{inst.short_name}</span></div>
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">Sistemas de origem</div>
        <div style={{ padding: 14 }}>
          {inst.sources.map((s) => (
            <dl className="kv" key={s.id}>
              <dt>Nome</dt><dd>{s.name}</dd>
              <dt>Base</dt><dd className="mono"><a className="link" href={s.base_url} target="_blank" rel="noreferrer">{s.base_url}</a></dd>
              {s.documentation_url && <><dt>Documentação</dt><dd className="mono"><a className="link" href={s.documentation_url} target="_blank" rel="noreferrer">{s.documentation_url}</a></dd></>}
            </dl>
          ))}
        </div>
      </section>
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">Cobertura</div>
        <table className="table">
          <thead><tr><th>Capacidade</th><th>Status</th><th>Registros</th><th>Último sucesso</th><th>Detalhe</th></tr></thead>
          <tbody>{caps.data?.map((c) => (
            <tr key={c.capability}>
              <td>{CAPABILITY_LABEL[c.capability] ?? c.capability}</td>
              <td><span className={`status ${c.status}`}>{STATUS_LABEL[c.status] ?? c.status}</span></td>
              <td className="mono">{c.record_count ?? '—'}</td>
              <td className="mono">{fmtDateTime(c.last_success_at)}</td>
              <td className="mono faint" style={{ fontSize: 10.5 }}>{c.note ?? JSON.stringify(c.coverage)}</td>
            </tr>))}</tbody>
        </table>
      </section>
      <section className="panel">
        <div className="panel-head">Execuções de ingestão</div>
        <table className="table">
          <thead><tr><th>Início</th><th>Escopo</th><th>Status</th><th>Conector</th><th>Estatísticas</th><th>Problemas</th></tr></thead>
          <tbody>{runs.data?.runs.map((r) => (
            <tr key={r.id}>
              <td className="mono">{fmtDateTime(r.started_at)}</td>
              <td>{r.scope.join(', ')}</td>
              <td><span className={`status ${r.status}`}>{r.status}</span></td>
              <td className="mono">{r.connector}@{r.connector_version}</td>
              <td className="mono faint" style={{ fontSize: 10.5 }}>{Object.entries(r.stats).filter(([, v]) => typeof v === 'number').map(([k, v]) => `${k}=${v}`).join(' ')}</td>
              <td className="faint" style={{ fontSize: 11 }}>{r.error ?? r.issues.map((i) => `${i.code} ×${i.count}`).join(', ')}</td>
            </tr>))}</tbody>
        </table>
      </section>
    </div>
  )
}
