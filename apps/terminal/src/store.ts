import { create } from 'zustand'

export type View = 'inicio' | 'analises' | 'congresso' | 'senado' | 'camara' | 'stf' | 'executivo' | 'partidos' | 'noticias' | 'sources'
export type SenadoTab = 'composicao' | 'votacoes' | 'presidencia2025' | 'presidencia2027' | 'proposicoes' | 'comissoes'

type State = {
  institutionId: string | null
  view: View
  analysisId: string | null
  agentDraft: string | null
  senadoTab: SenadoTab
  sidebarCollapsed: boolean
  selectedId: string | null
  hoveredId: string | null
  partyFilter: string | null
  search: string
  setInstitution: (id: string) => void
  setView: (v: View) => void
  setAnalysis: (id: string | null) => void
  setAgentDraft: (draft: string | null) => void
  setSenadoTab: (t: SenadoTab) => void
  toggleSidebar: () => void
  select: (id: string | null) => void
  hover: (id: string | null) => void
  setPartyFilter: (id: string | null) => void
  setSearch: (q: string) => void
}

export const useStore = create<State>((set) => ({
  institutionId: null,
  view: 'inicio',
  analysisId: null,
  agentDraft: null,
  senadoTab: 'composicao',
  sidebarCollapsed: readPref('politeia.sidebar') === 'collapsed',
  selectedId: null,
  hoveredId: null,
  partyFilter: null,
  search: '',
  setInstitution: (id) => set({ institutionId: id, selectedId: null, partyFilter: null, search: '', hoveredId: null }),
  setView: (view) => set({ view, selectedId: null, ...(view === 'analises' ? { analysisId: null } : {}) }),
  setAnalysis: (analysisId) => set({ view: 'analises', analysisId, selectedId: null }),
  setAgentDraft: (agentDraft) => set({ agentDraft }),
  setSenadoTab: (senadoTab) => set({ view: 'senado', senadoTab, selectedId: null }),
  toggleSidebar: () => set((s) => {
    writePref('politeia.sidebar', s.sidebarCollapsed ? 'open' : 'collapsed')
    return { sidebarCollapsed: !s.sidebarCollapsed }
  }),
  select: (selectedId) => set({ selectedId }),
  hover: (hoveredId) => set({ hoveredId }),
  setPartyFilter: (partyFilter) => set({ partyFilter }),
  setSearch: (search) => set({ search }),
}))

function readPref(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function writePref(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* preference is optional */ }
}
