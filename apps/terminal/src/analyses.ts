import type { View } from './store'

export const ANALYSES = [
  { id: 'caso-master', title: 'Caso Master', description: 'Atualizações, linha do tempo e caminhos institucionais.', scopes: ['Supremo Tribunal Federal', 'Senado', 'PGR'], view: null },
  { id: 'senado-2027', title: 'A sucessão no Senado', description: 'Presidência de 2027: cenários, apoios e incertezas.', scopes: ['Senado'], view: 'senado' as View },
  { id: 'votacoes', title: 'Como o Senado vota', description: 'Votos nominais, bancadas e limites do voto secreto.', scopes: ['Senado'], view: 'senado' as View },
]

export type Notebook = { id: string; title: string; question: string; notes: string }
export const NOTEBOOK_KEY = 'politeia.analises.v1'
export function loadNotebooks(): Notebook[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(NOTEBOOK_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((n): n is Notebook => n && typeof n.id === 'string' && n.id.startsWith('local-') && typeof n.title === 'string' && typeof n.question === 'string' && typeof n.notes === 'string') : []
  } catch { return [] }
}
