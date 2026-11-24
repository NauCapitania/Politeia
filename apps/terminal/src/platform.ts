import type { IconName } from '@blueprintjs/core'
import type { View } from './store'

// Shared navigation contract. Institutions are independent of thematic analyses.
export const SPACES: { view: View; label: string; aliases?: string[]; icon: IconName; group: 'Instituições' | 'Biblioteca' | null }[] = [
  { view: 'inicio', label: 'Central de situação', icon: 'control', group: null },
  { view: 'analises', label: 'Análises', icon: 'projects', group: null },
  { view: 'congresso', label: 'Congresso Nacional', icon: 'office', group: 'Instituições' },
  { view: 'senado', label: 'Senado Federal', icon: 'layout-circle', group: 'Instituições' },
  { view: 'camara', label: 'Câmara dos Deputados', icon: 'people', group: 'Instituições' },
  { view: 'stf', label: 'Supremo Tribunal Federal', aliases: ['STF'], icon: 'take-action', group: 'Instituições' },
  { view: 'executivo', label: 'Poder Executivo', icon: 'briefcase', group: 'Instituições' },
  { view: 'partidos', label: 'Partidos e financiamento', icon: 'git-branch', group: 'Biblioteca' },
  { view: 'noticias', label: 'Notícias', icon: 'feed', group: 'Biblioteca' },
  { view: 'sources', label: 'Fontes e cobertura', icon: 'database', group: 'Biblioteca' },
]

export const viewLabel = (view: View) => SPACES.find((s) => s.view === view)!.label
export const POWERS = [
  { id: 'legislativo', label: 'Legislativo', view: 'congresso' as const, views: ['congresso', 'senado', 'camara'] },
  { id: 'judiciario', label: 'Judiciário', view: 'stf' as const, views: ['stf'] },
  { id: 'executivo', label: 'Executivo', view: 'executivo' as const, views: ['executivo'] },
]
