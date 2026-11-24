import { useQuery, keepPreviousData } from '@tanstack/react-query'
import type { components } from './schema'

export type S = components['schemas']
export type Institution = S['Institution']
export type Capability = S['Capability']
export type Member = S['Member']
export type Composition = S['Composition']
export type Proposal = S['ProposalSummary']
export type Entity = S['Entity']
export type Relationship = S['Relationship']
export type Graph = S['Graph']
export type SourceRef = S['SourceRef']
export type SourceRecord = S['SourceRecord']
export type TimelineItem = S['TimelineItem']
export type IngestionRun = S['IngestionRun']
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, params?: Record<string, string | number | undefined | null>): Promise<T> {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  const res = await fetch(`/v1${path}${qs.size ? `?${qs}` : ''}`)
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const useInstitutions = () => useQuery({ queryKey: ['institutions'], queryFn: () => api<Institution[]>('/institutions') })

export const useCapabilities = (id?: string) =>
  useQuery({ queryKey: ['capabilities', id], queryFn: () => api<Capability[]>(`/institutions/${id}/capabilities`), enabled: !!id })

export const useComposition = (id?: string) =>
  useQuery({ queryKey: ['composition', id], queryFn: () => api<Composition>(`/institutions/${id}/composition`), enabled: !!id })

export const useMembers = (id: string | undefined, params: { q?: string; party?: string; unit?: string }) =>
  useQuery({
    queryKey: ['members', id, params],
    queryFn: () => api<Page<Member>>(`/institutions/${id}/members`, { ...params, limit: 500 }),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })

export const useProposals = (id: string | undefined, params: { q?: string; type_code?: string; author?: string; offset?: number }) =>
  useQuery({
    queryKey: ['proposals', id, params],
    queryFn: () => api<Page<Proposal>>(`/institutions/${id}/proposals`, { ...params, limit: 50 }),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })

export const useProposalTypes = (id?: string) =>
  useQuery({
    queryKey: ['proposal-types', id],
    queryFn: () => api<{ type_code: string; type_name: string; count: number }[]>(`/institutions/${id}/proposal-types`),
    enabled: !!id,
  })

export const useGraph = (id: string | undefined, focus?: string | null) =>
  useQuery({
    queryKey: ['graph', id, focus],
    queryFn: () => api<Graph>(`/institutions/${id}/graph`, { focus: focus ?? undefined }),
    enabled: !!id,
    placeholderData: keepPreviousData,
  })

export const useEntity = (id?: string | null) =>
  useQuery({ queryKey: ['entity', id], queryFn: () => api<Entity>(`/entities/${id}`), enabled: !!id })

export const useRelationships = (id?: string | null) =>
  useQuery({ queryKey: ['relationships', id], queryFn: () => api<Relationship[]>(`/entities/${id}/relationships`), enabled: !!id })

export const useTimeline = (id?: string | null) =>
  useQuery({ queryKey: ['timeline', id], queryFn: () => api<TimelineItem[]>(`/entities/${id}/timeline`), enabled: !!id })

export const useSource = (ref?: SourceRef | null) =>
  useQuery({
    queryKey: ['source', ref?.raw_record_id, ref?.json_path],
    queryFn: () => api<SourceRecord>(`/sources/${ref!.raw_record_id}`, { path: ref!.json_path }),
    enabled: !!ref,
  })

export const useIngestion = (institution?: string) =>
  useQuery({
    queryKey: ['ingestion', institution],
    queryFn: () => api<{ runs: IngestionRun[] }>('/ingestion/status', { institution }),
    enabled: !!institution,
  })

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Src = { url: string; outlet: string; date?: string | null; kind: string }
export type SeatRow = {
  person_id: string; code?: string; name: string; full_name?: string | null; photo_url?: string; uf?: string; party?: string | null
  participation: string; exercise_start?: string; exercise_end?: string | null; mandate_end?: string | null
}
const get = <T,>(path: string, params?: Record<string, string | number | undefined | null>) => () => api<T>(path, params)
export const useSeats = (data: string) =>
  useQuery({ queryKey: ['seats', data], queryFn: get<{ date: string; observed: number; seats: SeatRow[]; note?: string }>('/senado/composicao', { data }), placeholderData: keepPreviousData })
export const useChanges = () => useQuery({ queryKey: ['changes'], queryFn: get<any[]>('/senado/mudancas') })
export const useSenator = (id?: string | null) =>
  useQuery({ queryKey: ['senator', id], queryFn: get<any>(`/senadores/${id}`), enabled: !!id })
export const useVotes = (q?: string, secreta?: string, limit = 200) =>
  useQuery({ queryKey: ['votes', q, secreta, limit], queryFn: get<any[]>('/votacoes', { q, secreta, limit }), placeholderData: keepPreviousData })
export const useVote = (id?: string | null) => useQuery({ queryKey: ['vote', id], queryFn: get<any>(`/votacoes/${id}`), enabled: !!id })
export const useNews = (tema?: string, entidade?: string) =>
  useQuery({ queryKey: ['news', tema, entidade], queryFn: get<any[]>('/noticias', { tema, entidade, limit: 120 }), placeholderData: keepPreviousData })
export const useDossier = (d: string) => useQuery({ queryKey: ['dossier', d], queryFn: get<any>(`/dossies/${d}`) })
export const usePres2025 = () => useQuery({ queryKey: ['pres2025'], queryFn: get<any>('/presidencia/2025') })
export const usePres2027 = () => useQuery({ queryKey: ['pres2027'], queryFn: get<any>('/presidencia/2027') })
export const useSeats2027 = (enabled: boolean) =>
  useQuery({ queryKey: ['seats-2027'], queryFn: get<any>('/senado/composicao/2027'), enabled })
export const useCommittees = () => useQuery({ queryKey: ['committees'], queryFn: get<any[]>('/comissoes') })
export const useCommittee = (id?: string | null) =>
  useQuery({ queryKey: ['committee', id], queryFn: get<any>(`/comissoes/${id}`), enabled: !!id })
