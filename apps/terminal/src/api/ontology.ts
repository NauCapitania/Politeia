import { useQuery } from '@tanstack/react-query'
import { api, type Src } from './client'

export type Power = { id: string; name: string; description: string; constitutional: boolean }
export type Body = { id: string; name: string; acronym: string | null; power_id: string; parent_id: string | null; description: string | null; holders: number; seats: number | null; origin: string; legal_basis_id: string | null; institution_id: string | null }
export type Office = { id: string; name: string; body_id: string | null; description: string | null; holders: number; seats: number | null; term_years: number | null; provision: string; legal_basis_id: string | null }
export type Competence = { id: string; holder_body_id: string | null; holder_office_id: string | null; target_body_id: string | null; target_office_id: string | null; verb: string; target_label: string; description: string | null; legal_basis_id: string; provision: string | null; quorum: string | null }
export type Ontology = {
  powers: Power[]; bodies: Body[]; offices: Office[]; competences: Competence[];
  legal_bases: { id: string; norm: string; provision: string | null; url: string }[];
  holdings: { id: string; person_id: string; person_name: string | null; office_id: string; body_id: string | null; party: string | null; represented_unit: string | null; nominated_by: string | null; since: string | null; origin?: string; sources?: Src[] }[];
  analyses: { id: string; title: string; entities: { entity_kind: string; entity_id: string; role: string }[] }[];
}
export const useOntology = () => useQuery({ queryKey: ['ontology'], queryFn: () => api<Ontology>('/ontologia') })
export const useObservedLinks = (institution?: string | null) => useQuery({ queryKey: ['ontology-links', institution], queryFn: () => api<{ note: string; links: { a: string; b: string; weight: number; shared: number }[] }>(`/ontologia/ligacoes/${institution}`), enabled: !!institution })
export function competenceBody(data: Ontology, c: Competence, side: 'holder' | 'target') {
  return c[`${side}_body_id`] ?? data.offices.find((o) => o.id === c[`${side}_office_id`])?.body_id ?? null
}
