import { create } from 'zustand'

export type View = 'overview' | 'people' | 'proposals' | 'graph' | 'sources'

type State = {
  institutionId: string | null
  view: View
  selectedId: string | null
  hoveredId: string | null
  partyFilter: string | null
  search: string
  setInstitution: (id: string) => void
  setView: (v: View) => void
  select: (id: string | null) => void
  hover: (id: string | null) => void
  setPartyFilter: (id: string | null) => void
  setSearch: (q: string) => void
}

export const useStore = create<State>((set) => ({
  institutionId: null,
  view: 'overview',
  selectedId: null,
  hoveredId: null,
  partyFilter: null,
  search: '',
  setInstitution: (id) => set({ institutionId: id, selectedId: null, partyFilter: null, search: '', hoveredId: null }),
  setView: (view) => set({ view }),
  select: (selectedId) => set({ selectedId }),
  hover: (hoveredId) => set({ hoveredId }),
  setPartyFilter: (partyFilter) => set({ partyFilter }),
  setSearch: (search) => set({ search }),
}))
