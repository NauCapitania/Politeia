import { useState } from 'react'
import { Icon } from '@blueprintjs/core'
import { ANALYSES, loadNotebooks, NOTEBOOK_KEY, type Notebook } from '../analyses'
import { useStore } from '../store'
import { MasterAnalysis } from './MasterAnalysis'

export function Analises() {
  const { analysisId, setAnalysis, setView, setSenadoTab, setAgentDraft } = useStore()
  const [notebooks, setNotebooks] = useState(loadNotebooks)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')
  const [saveError, setSaveError] = useState(false)
  const current = notebooks.find((n) => n.id === analysisId)

  function save(next: Notebook[]) {
    setNotebooks(next)
    try { localStorage.setItem(NOTEBOOK_KEY, JSON.stringify(next)); setSaveError(false) } catch { setSaveError(true) }
  }
  function open(id: string) {
    if (id === 'senado-2027' || id === 'votacoes') setSenadoTab(id === 'senado-2027' ? 'presidencia2027' : 'votacoes')
    else setAnalysis(id)
  }
  const notice = <p className={saveError ? 'warn-text' : 'muted small'} role="status">{saveError ? 'Não foi possível salvar neste navegador. Copie suas notas antes de sair.' : 'Cadernos pessoais ficam somente neste navegador; não são sincronizados nem coletam dados automaticamente.'}</p>
  if (analysisId === 'caso-master') return <><div className="analysis-back"><button className="quiet-button" onClick={() => setAnalysis(null)}><Icon icon="arrow-left" size={12} /> Todas as análises</button></div><MasterAnalysis /></>
  if (current) return <div className="view">
    <button className="quiet-button mb" onClick={() => setAnalysis(null)}><Icon icon="arrow-left" size={12} /> Todas as análises</button>
    <div className="eyebrow">CADERNO PESSOAL · ANÁLISE EXPLORATÓRIA</div><h1>{current.title}</h1>
    <p className="lede">{current.question}</p>{notice}
    <button className="quiet-button mb" onClick={() => setAgentDraft(`Análise: ${current.title}\nPergunta: ${current.question}\nInvestigue com fontes e datas, distinguindo fatos, declarações e hipóteses.`)}>Investigar com o agente →</button>
    <label className="notebook-label" htmlFor="analysis-notes">Evidências, links e hipóteses</label>
    <textarea id="analysis-notes" className="notebook-notes" maxLength={40000} value={current.notes} placeholder="Registre a data e a fonte de cada fato. Separe hipóteses de conclusões." onChange={(e) => save(notebooks.map((n) => n.id === current.id ? { ...n, notes: e.target.value } : n))} />
    <h2>Explore as conexões</h2><p className="muted">Consulte as instituições e use o agente para formular perguntas com fontes. Notas pessoais não são evidências verificadas.</p>
    <div className="toolbar"><button className="quiet-button" onClick={() => setView('congresso')}>Congresso Nacional →</button><button className="quiet-button" onClick={() => setView('stf')}>Supremo Tribunal Federal →</button><button className="quiet-button" onClick={() => setView('executivo')}>Poder Executivo →</button><button className="quiet-button" onClick={() => setView('partidos')}>Partidos →</button></div>
  </div>
  return <div className="view">
    <div className="overview-heading"><div><div className="eyebrow">CONEXÕES, NÃO SILOS</div><h1>Análises</h1><p>Uma plataforma, várias perguntas. Cada análise reúne um recorte dos dados institucionais.</p></div><button className="quiet-button" onClick={() => setCreating((v) => !v)} aria-expanded={creating}><Icon icon="add" size={14} /> Nova análise</button></div>
    {creating && <form className="card analysis-form mb" onSubmit={(e) => { e.preventDefault(); if (!title.trim() || !question.trim()) return; const id = `local-${crypto.randomUUID()}`; save([...notebooks, { id, title: title.trim(), question: question.trim(), notes: '' }]); setCreating(false); setTitle(''); setQuestion(''); setAnalysis(id) }}>
      <label>Título<input required maxLength={100} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex.: tramitação da reforma tributária" /></label>
      <label>Pergunta de análise<textarea required maxLength={1000} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="O que você quer entender e quais conexões investigar?" /></label>
      <button className="quiet-button" type="submit">Criar caderno</button>{notice}
    </form>}
    <div className="analysis-grid">{ANALYSES.map((a, i) => <button key={a.id} className={`workspace-card analysis-tile ${i === 0 ? 'featured' : ''}`} onClick={() => open(a.id)}><span className="eyebrow">{i === 0 ? 'EM FOCO' : 'ANÁLISE INSTITUCIONAL'}</span><Icon icon={i === 0 ? 'timeline-events' : 'chart'} size={25} /><h2>{a.title}</h2><p>{a.description}</p><span className="analysis-scopes">{a.scopes.join(' · ')}</span><span className="analysis-open">Explorar análise <Icon icon="arrow-right" size={14} /></span></button>)}</div>
    <h2>Seus cadernos</h2>{notice}
    {notebooks.length ? <div className="analysis-grid">{notebooks.map((n) => <button className="workspace-card analysis-tile" key={n.id} onClick={() => setAnalysis(n.id)}><span className="eyebrow">PESSOAL · NESTE NAVEGADOR</span><h2>{n.title}</h2><p>{n.question}</p><span className="analysis-open">Abrir caderno →</span></button>)}</div> : <p className="muted">Comece pela sua pergunta. Crie um caderno para organizar outra análise política.</p>}
  </div>
}
