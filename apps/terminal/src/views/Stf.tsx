import { Spinner } from '@blueprintjs/core'
import { useDossier } from '../api/client'
import { InstitutionGuide } from '../components/InstitutionGuide'
import { InstitutionMasthead } from '../components/InstitutionMasthead'
import { SrcList } from '../components/SrcList'
import { fmtDate } from '../format'
import { useStore } from '../store'

export function Stf() {
  const q = useDossier('stf-caso-master')
  const setAnalysis = useStore((s) => s.setAnalysis)
  const ministers = q.data?.items?.minister ?? []
  return <div className="view">
    <InstitutionMasthead kind="stf" eyebrow="PODER JUDICIÁRIO · TRIBUNAL CONSTITUCIONAL" title="Supremo Tribunal Federal" subtitle="A Constituição como referência. A instituição além de cada caso." />
    <p className="lede">Conheça a instituição, suas competências e sua composição. Casos específicos ficam em espaços de análise próprios.</p>
    <InstitutionGuide kind="stf" expanded />
    <h2>Composição na base</h2><p className="muted">Cadastro curado; não é uma consulta em tempo real. A associação de uma pessoa a um caso não define sua atuação institucional.</p>
    {q.isLoading && <Spinner size={22} />}
    {q.isError && <p className="warn-text">Não foi possível consultar a composição nesta tentativa.</p>}
    {!q.isLoading && !q.isError && !ministers.length && <p className="muted">Composição ainda não disponível na base.</p>}
    <div className="minister-roster">{ministers.map((m: any) => <article className="card" key={m.id}><h3>{m.name}</h3><p className="muted small">{m.role ?? 'Ministro'}</p>{m.nominated_by && <p className="small">Indicação: {m.nominated_by} · posse: {fmtDate(m.took_office)}</p>}<SrcList sources={m.sources} hidePress /></article>)}</div>
    <section className="card analysis-entry"><div><div className="eyebrow">ANÁLISE EM FOCO</div><h2>Caso Master</h2><p>Atualizações, relatos, linha do tempo e caminhos institucionais, separados do cadastro do tribunal.</p></div><button className="quiet-button" onClick={() => setAnalysis('caso-master')}>Abrir análise do caso Master →</button></section>
  </div>
}
