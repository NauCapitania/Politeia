import { useQuery } from '@tanstack/react-query'
import { api, useDossier } from '../../api/client'

export type Ref = { url: string; title?: string | null; date?: string | null; outlet?: string | null }
export type Term = {
  id: string; person_id: string; name: string; profile_url?: string | null; party?: string | null; uf?: string | null
  interim: boolean; start: string; end?: string | null; end_note?: string | null; current: boolean
  epistemic_status: string; refs: Ref[]; senate_person_id?: string | null
}
export type Entity = { code: string; name: string; acronym?: string | null; legal_nature?: string | null; site?: string | null; direct: boolean }
export type Kind = 'presidencia' | 'ministerio' | 'orgao_ministerial' | 'entidade'
export type Body = {
  code: string; name: string; acronym?: string | null; kind: Kind; legal_nature?: string | null
  competence?: string | null; purpose?: string | null; mission?: string | null; legal_basis?: string | null; site?: string | null
  administrative_units: number; archive_month?: string | null; version_start?: string | null
  entities: Entity[]; holder: Term | null; terms: Term[]
}
export type Executivo = {
  institution_id: string
  presidency: { code: string; name: string; competence?: string | null; legal_basis?: string | null; site?: string | null } | null
  counts: { bodies: number; top_level: number; ministries: number; entities: number; ministers_in_office: number; terms: number }
  bodies: Body[]
  unmatched: { ministry: string | null; title: string; terms: Term[] }[]
  sources: { id: string; name: string; url: string; last_success_at?: string | null }[]
}

export const KIND_LABEL: Record<Kind, string> = {
  presidencia: 'Presidência da República',
  ministerio: 'Ministérios',
  orgao_ministerial: 'Órgãos com status de ministério',
  entidade: 'Entidades ligadas à Presidência',
}

export const useExecutivo = () => useQuery({ queryKey: ['executivo'], queryFn: () => api<Executivo>('/executivo') })
export const useExecutivoGuide = () => useDossier('poder-executivo')

/** Sum of the parties of the ministers in office; null party means "sem partido". */
export function partyCounts(bodies: Body[]): { party: string | null; n: number }[] {
  const acc = new Map<string | null, number>()
  for (const b of bodies) if (b.holder) acc.set(b.holder.party ?? null, (acc.get(b.holder.party ?? null) ?? 0) + 1)
  return [...acc.entries()].map(([party, n]) => ({ party, n })).sort((a, b) => b.n - a.n || String(a.party).localeCompare(String(b.party)))
}

export const shortName = (b: Pick<Body, 'name'>) =>
  b.name.replace(/^Ministério (da|do|das|dos|de) /, '').replace(/ da Presidência da República$/, '')
