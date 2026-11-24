import { useStore, type View } from '../store'

const CONSTITUTION = 'https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm'
const GUIDES = {
  congresso: { title: 'Como funciona o Congresso', text: 'O Legislativo federal é bicameral: a Câmara representa o povo e o Senado representa os estados e o Distrito Federal. As casas têm competências próprias e também se reúnem em sessão conjunta.', powers: 'Legislar, deliberar sobre o orçamento e fiscalizar o Executivo com auxílio do Tribunal de Contas da União.', limits: 'Uma proposta aprovada em uma casa não vira lei automaticamente. O rito depende do tipo de matéria; competências privativas não passam pelas duas casas.', articles: '44, 48 a 52 e 70', anchor: 'art44' },
  senado: { title: 'Como funciona o Senado', text: 'São 81 cadeiras: três por estado e pelo Distrito Federal. O mandato é de oito anos, com renovação alternada de um terço e dois terços a cada quatro anos.', powers: 'Revisar ou iniciar leis, sabatinar e aprovar autoridades nos casos constitucionais e processar e julgar autoridades por crimes de responsabilidade nas hipóteses do art. 52.', limits: 'O presidente do Senado conduz os trabalhos; não substitui a deliberação coletiva. Votos secretos não revelam a escolha individual de cada senador.', articles: '46 e 52', anchor: 'art46' },
  camara: { title: 'Como funciona a Câmara', text: 'Deputados representam o povo, eleitos pelo sistema proporcional em cada estado e no Distrito Federal, para mandatos de quatro anos.', powers: 'Propor, discutir e votar leis, fiscalizar o governo e autorizar, por dois terços, a instauração de processo contra o presidente e o vice-presidente da República, nas hipóteses constitucionais.', limits: 'A autorização da Câmara não é julgamento final de crime de responsabilidade: esse julgamento compete ao Senado.', articles: '45 e 51', anchor: 'art45' },
  stf: { title: 'O que faz o Supremo', text: 'O Supremo Tribunal Federal é um dos órgãos do Judiciário e tem como função principal guardar a Constituição. Não se confunde com todo o Poder Judiciário.', powers: 'Julgar ações de controle de constitucionalidade, recursos extraordinários e processos de sua competência originária. Tem 11 ministros, nomeados pelo presidente da República após aprovação da maioria absoluta do Senado.', limits: 'O tribunal julga; não exerce a função de acusação da PGR nem a investigação policial. Competência, relatoria e instância de decisão dependem do processo.', articles: '92, 101 e 102', anchor: 'art101' },
  executivo: { title: 'Como funciona o Executivo', text: 'O presidente da República exerce o Poder Executivo federal, auxiliado pelos ministros de Estado. Os ministérios dirigem áreas da administração pública federal.', powers: 'Executar políticas e o orçamento, propor projetos, sancionar ou vetar leis, editar decretos e, nos requisitos constitucionais, medidas provisórias.', limits: 'Decretos não substituem livremente a lei. O Executivo está sujeito à fiscalização do Congresso e ao controle judicial de legalidade e constitucionalidade.', articles: '76, 84 e 87', anchor: 'art76' },
  comissoes: { title: 'O que uma comissão pode fazer', text: 'Comissões distribuem o trabalho por tema. O relator analisa uma matéria e propõe um parecer; a comissão debate e delibera conforme o regimento e o despacho de distribuição.', powers: 'Examinar proposições, realizar audiências, ouvir autoridades e fiscalizar políticas. Em hipóteses regimentais, podem aprovar projetos sem passar pelo plenário, ressalvado recurso.', limits: 'Uma CPI investiga fato determinado por prazo certo; não condena criminalmente. Parecer, aprovação em comissão e aprovação final são etapas diferentes. Cada comissão tem competências regimentais específicas.', articles: '58', anchor: 'art58' },
}
export type GuideKind = keyof typeof GUIDES

export function InstitutionGuide({ kind, expanded = false }: { kind: GuideKind; expanded?: boolean }) {
  const guide = GUIDES[kind]
  return <details className="institution-guide" open={expanded || undefined}>
    <summary>{guide.title}<span>Competências e limites</span></summary>
    <div className="guide-body"><p>{guide.text}</p><div className="guide-columns"><div><h3>O que pode fazer</h3><p>{guide.powers}</p></div><div><h3>O que não significa</h3><p>{guide.limits}</p></div></div>
      <a className="link small" href={`${CONSTITUTION}#${guide.anchor}`} target="_blank" rel="noreferrer">Fonte oficial: Constituição Federal, arts. {guide.articles} ↗</a>
      {kind === 'comissoes' && <p><a className="link small" href="https://www25.senado.leg.br/web/atividade/regimento-interno" target="_blank" rel="noreferrer">Regimento Interno do Senado: competências de cada comissão ↗</a></p>}
    </div>
  </details>
}

export function PowerMap() {
  const setView = useStore((s) => s.setView)
  const nodes: { view: View; title: string; body: string; relation: string }[] = [
    { view: 'congresso', title: 'Legislativo', body: 'Câmara + Senado', relation: 'Leis, orçamento e fiscalização' },
    { view: 'executivo', title: 'Executivo', body: 'Presidência + ministérios', relation: 'Políticas públicas, sanção e veto' },
    { view: 'stf', title: 'Judiciário', body: 'Supremo Tribunal Federal neste recorte', relation: 'Guarda da Constituição e julgamentos' },
  ]
  return <section className="power-map" aria-label="Mapa de relações entre os poderes">
    <div className="eyebrow">INDEPENDENTES E HARMÔNICOS ENTRE SI</div><h2>Como o poder se conecta</h2>
    <div className="power-nodes">{nodes.map((n) => <button key={n.view} onClick={() => setView(n.view)}><span>{n.title}</span><b>{n.body}</b><small>{n.relation}</small></button>)}</div>
    <div className="power-relations"><p><b>Congresso → Executivo</b> Fiscaliza, aprova o orçamento e aprecia vetos e medidas provisórias.</p><p><b>Executivo → Congresso</b> Propõe leis e orçamento; sanciona ou veta projetos de lei.</p><p><b>Senado → Supremo</b> Aprova indicações de ministros; julga crimes de responsabilidade nas hipóteses legais.</p><p><b>Supremo → poderes públicos</b> Controla a constitucionalidade de atos, nos processos de sua competência.</p></div>
    <p className="small muted">A PGR integra o Ministério Público, não um dos três poderes. Atua na defesa da ordem jurídica e promove a ação penal pública na sua competência (arts. 127 e 129).</p>
    <a className="link small" href={`${CONSTITUTION}#art2`} target="_blank" rel="noreferrer">Base: Constituição Federal, arts. 2º, 48–52, 66, 84, 101–102 e 127–129 ↗</a>
  </section>
}
