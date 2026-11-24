import { useQuery } from '@tanstack/react-query'
import { api, isStatic, useComposition } from './client'

export const CAMARA = 'ins_br_camara'

export type CamaraVote = {
  id: string; date: string | null; description: string | null; matter: string | null; result: string | null
  totals: Record<string, number>; nominal: boolean | null; secret: boolean; proposal_id: string | null
}
export type CamaraBallot = { person_id: string; name: string; party: string | null; uf: string | null; vote: string | null; label: string | null }
export type CamaraVoteDetail = CamaraVote & { votes: CamaraBallot[] }
export type CamaraCommittee = {
  id: string; abbreviation: string | null; name: string; type: string | null; subtitle: string | null
  chair: string | null; titulares: number; suplentes: number; last_observed_at: string | null
}
export type CamaraCommitteeMember = {
  person_id: string; name: string; photo_url: string | null; seat_kind: string; role: string | null
  party: string | null; uf: string | null; since: string | null
}
export type CamaraCommitteeDetail = Omit<CamaraCommittee, 'chair' | 'titulares' | 'suplentes' | 'subtitle'> & {
  attributes: Record<string, any>; members: CamaraCommitteeMember[]
}
export type PartySwitch = { person_id: string; name: string; photo_url: string | null; date: string; from: string; to: string }

const matches = (q: string, ...fields: (string | null | undefined)[]) =>
  !q || fields.some((f) => f?.toLocaleLowerCase('pt-BR').includes(q.toLocaleLowerCase('pt-BR')))

export const useCamaraComposition = () => useComposition(CAMARA)

export const useCamaraVotes = (q: string, nominal: boolean | undefined, limit: number) =>
  useQuery({
    queryKey: ['camara-votes', isStatic() ? '' : q, nominal, isStatic() ? 0 : limit],
    queryFn: () => api<CamaraVote[]>('/camara/votacoes', isStatic() ? {} : { q, nominal: nominal === undefined ? undefined : String(nominal), limit }),
    select: (rows) => rows.filter((v) => matches(q, v.description, v.matter) && (nominal === undefined || (nominal ? !!v.nominal : !v.nominal && !v.secret))).slice(0, limit),
  })

export const useCamaraVote = (id?: string | null) =>
  useQuery({ queryKey: ['camara-vote', id], queryFn: () => api<CamaraVoteDetail>(`/camara/votacoes/${id}`), enabled: !!id })

export const useCamaraCommittees = () =>
  useQuery({ queryKey: ['camara-committees'], queryFn: () => api<CamaraCommittee[]>('/camara/comissoes') })

export const useCamaraCommittee = (id?: string | null) =>
  useQuery({ queryKey: ['camara-committee', id], queryFn: () => api<CamaraCommitteeDetail>(`/camara/comissoes/${id}`), enabled: !!id })

export const useCamaraSwitches = () =>
  useQuery({ queryKey: ['camara-switches'], queryFn: () => api<PartySwitch[]>('/camara/trocas') })
