import type { Src } from '../../api/client'

type Sourced = { id: string; sources: Src[] }

export type Party = Sourced & { partyId: string; name: string; abbreviation: string }
export const eventTypes = {
  fundacao: 'Fundação e origem',
  registro: 'Registro no TSE',
  fusao: 'Fusão',
  incorporacao: 'Incorporação',
  renomeacao: 'Mudança de nome',
  extincao: 'Extinção',
  federacao: 'Federação',
  contexto: 'Contexto histórico',
} as const
export type LineageEvent = Sourced & {
  type: keyof typeof eventTypes
  date: string
  from: string[]
  to: string[]
  title: string
  summary: string
  people?: string[]
  declared?: string
  analysis?: string
}

export const fundNames = { fefc: 'Fundo Eleitoral (FEFC)', partidario: 'Fundo Partidário' } as const
export type Fund = keyof typeof fundNames
export type Funding = Sourced & {
  fund: Fund
  year: number
  totalCents: number
  budgetCents?: number
  finesCents?: number
  partial?: boolean
  allocations: { partyId: string; cents: number }[]
  note: string
}
type Side = { year: number; partyIds: string[] }
export type Comparison = Sourced & { fund: Fund; title: string; before: Side; after: Side; text: string }
export type Analysis = Sourced & { section?: 'sites' | 'coverage'; title: string; text: string }
export type PartySite = Sourced & { partyId: string; title: string; text: string }

export type PartyDossier = {
  as_of: string
  items: {
    party: Party[]
    event: LineageEvent[]
    funding: Funding[]
    comparison?: Comparison[]
    analysis?: Analysis[]
    site?: PartySite[]
  }
}

const reais = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const percent = new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 2 })
const compact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 2 })
const monthName = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
export const money = (cents: number) => reais.format(cents / 100)
export const share = (cents: number, total: number) => percent.format(cents / total)
export const compactMoney = (cents: number) => `R$ ${compact.format(cents / 100)}`
export const milestoneCount = (count: number, historical = false) => count === 1
  ? `1 marco${historical ? ' histórico' : ''}`
  : `${count} marcos${historical ? ' históricos' : ''}`
export function dateLabel(date: string) {
  if (date.length === 4) return date
  if (date.length === 7) return monthName.format(new Date(`${date}-01T00:00:00Z`))
  return date.split('-').reverse().join('/')
}
