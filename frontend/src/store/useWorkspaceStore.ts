import { create } from 'zustand'
import type { LeadCard, ResearchContract } from '../lib/types'

type WorkspaceState = {
  selectedLead: LeadCard | null
  result: ResearchContract | null
  setSelectedLead: (lead: LeadCard | null) => void
  setResult: (result: ResearchContract | null) => void
  reset: () => void
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedLead: null,
  result: null,
  setSelectedLead: (selectedLead) => set({ selectedLead }),
  setResult: (result) => set({ result, selectedLead: result?.leads[0] ?? null }),
  reset: () => set({ selectedLead: null, result: null }),
}))
