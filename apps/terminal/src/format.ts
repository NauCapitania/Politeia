const PALETTE = [
  '#5b8def', '#e07b53', '#4fb39a', '#c9a227', '#a77bd6', '#d0607a', '#62a8c8', '#8fb35a',
  '#c98b5b', '#7c8fd6', '#5fbfb0', '#d58fb8', '#9aa65a', '#b07858', '#6c9fd0', '#c4b55e',
]

export function partyColor(abbr?: string | null): string {
  if (!abbr) return '#4a5568'
  let h = 0
  for (const c of abbr.normalize('NFKD').toUpperCase()) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

export const fmtDate = (d?: string | null) =>
  d ? new Date(d.length === 10 ? `${d}T12:00:00` : d).toLocaleDateString('pt-BR') : '—'

export const fmtDateTime = (d?: string | null) =>
  d ? new Date(d).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—'

export const STATUS_LABEL: Record<string, string> = {
  available: 'Disponível',
  partial: 'Parcial',
  empty: 'Vazio',
  stale: 'Desatualizado',
  ingestion_failed: 'Falha na ingestão',
  not_ingested: 'Não ingerido',
  unavailable_in_source: 'Indisponível na fonte',
}

export const CAPABILITY_LABEL: Record<string, string> = {
  members: 'Membros atuais',
  mandates: 'Mandatos',
  party_composition: 'Composição partidária',
  party_history: 'Histórico partidário',
  proposals: 'Proposições',
  proposal_authors: 'Autoria',
  proposal_events: 'Tramitação',
  committees: 'Comissões',
  votes: 'Votações',
}

export const EPISTEMIC_LABEL: Record<string, string> = {
  verified: 'verificado',
  extracted: 'extraído',
  conflicting: 'em conflito',
  unknown: 'desconhecido',
  derived: 'derivado',
}

export const PARTICIPATION_LABEL: Record<string, string> = {
  holder: 'Titular',
  substitute_in_exercise: 'Suplente em exercício',
}
