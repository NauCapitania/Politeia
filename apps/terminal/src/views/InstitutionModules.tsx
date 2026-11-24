import type { ComponentType } from 'react'
import { InstitutionGuide, type GuideKind } from '../components/InstitutionGuide'

// Each independently delivered module plugs into the frame by its named export.
// Eager glob keeps standalone frame builds working until those modules land.
const modules = import.meta.glob<Record<string, ComponentType>>(['./Camara.tsx', './Executivo.tsx', './Partidos.tsx'], { eager: true })

function PendingModule({ title, kind }: { title: string; kind?: GuideKind }) {
  return <div className="view"><h1>{title}</h1><p className="lede">Este espaço está preparado. A cobertura de dados ainda não está integrada nesta versão; isso não significa ausência de atividade.</p>{kind && <InstitutionGuide kind={kind} expanded />}</div>
}
export function CamaraModule() { const View = modules['./Camara.tsx']?.Camara; return View ? <><div className="module-guide"><InstitutionGuide kind="camara" /></div><View /></> : <PendingModule title="Câmara dos Deputados" kind="camara" /> }
export function ExecutivoModule() { const View = modules['./Executivo.tsx']?.Executivo; return View ? <><div className="module-guide"><InstitutionGuide kind="executivo" /></div><View /></> : <PendingModule title="Poder Executivo" kind="executivo" /> }
export function PartidosModule() { const View = modules['./Partidos.tsx']?.Partidos; return View ? <View /> : <PendingModule title="Partidos e financiamento" /> }
