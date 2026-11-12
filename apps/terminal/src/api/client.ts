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
