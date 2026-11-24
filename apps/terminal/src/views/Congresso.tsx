import { useState } from 'react'
import { InstitutionGuide, PowerMap } from '../components/InstitutionGuide'
import { InstitutionMasthead } from '../components/InstitutionMasthead'
import { useStore } from '../store'

const STEPS = [
  { title: 'Iniciativa', text: 'A proposta é apresentada por quem tem iniciativa constitucional. Algumas matérias são reservadas a autoridades ou órgãos específicos.' },
  { title: 'Comissões', text: 'A matéria é distribuída às comissões competentes. Relatores propõem pareceres; podem ocorrer audiências e emendas. O rito pode ser conclusivo ou terminativo, sujeito a recurso.' },
  { title: 'Deliberação nas casas', text: 'Em regra, Câmara e Senado apreciam projetos de lei. A casa revisora pode aprovar, rejeitar ou emendar; emendas podem devolver o texto à casa iniciadora.' },
  { title: 'Sanção ou veto', text: 'Projetos de lei aprovados seguem ao presidente, que pode sancionar ou vetar. O Congresso pode rejeitar o veto. PECs seguem rito próprio: dois turnos e três quintos em cada casa, sem sanção presidencial.' },
  { title: 'Publicação e efeitos', text: 'A publicação oficial e a regra de vigência definem quando a norma produz efeitos. Aprovação política, publicação e execução da política pública não são a mesma coisa.' },
]

export function Congresso() {
  const [step, setStep] = useState(0)
  const setView = useStore((s) => s.setView)
  return <div className="view">
    <InstitutionMasthead kind="congresso" eyebrow="PODER LEGISLATIVO FEDERAL" title="Congresso Nacional" subtitle="Duas casas. Um processo de construção das decisões públicas." />
    <p className="lede">Duas casas, atribuições compartilhadas e competências próprias. Explore as instituições e o caminho das decisões.</p>
    <div className="congress-cards"><button className="workspace-card" onClick={() => setView('camara')}><span className="eyebrow">REPRESENTAÇÃO DO POVO</span><h2>Câmara dos Deputados →</h2><p>Iniciativa, deliberação e fiscalização.</p></button><button className="workspace-card" onClick={() => setView('senado')}><span className="eyebrow">ESTADOS E DISTRITO FEDERAL</span><h2>Senado Federal →</h2><p>Composição, votações, comissões e proposições.</p></button></div>
    <InstitutionGuide kind="congresso" expanded />
    <section className="legislative-process"><div className="eyebrow">DA PROPOSTA À NORMA</div><h2>Como um projeto avança</h2><p className="muted">Roteiro explicativo, não andamento de uma proposição específica. Urgência, tipo de matéria e regimentos podem alterar o percurso.</p>
      <div className="process-stages" aria-label="Etapas do processo legislativo">{STEPS.map((s, i) => <button key={s.title} aria-pressed={step === i} onClick={() => setStep(i)}><span>{i + 1}</span>{s.title}</button>)}</div>
      <div className="card" aria-live="polite"><h3>{STEPS[step].title}</h3><p>{STEPS[step].text}</p></div>
      <p><a className="link small" href="https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm#art59" target="_blank" rel="noreferrer">Fonte: Constituição Federal, arts. 59 a 69 ↗</a></p>
    </section>
    <InstitutionGuide kind="comissoes" /><PowerMap />
  </div>
}
