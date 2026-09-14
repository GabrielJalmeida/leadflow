import type {
  ContactPreparation,
  LibraryResponse,
  LifecycleStatus,
  QueueResponse,
  FollowUpResponse,
  LeadFlowSettings,
  InteractionResponse,
  Health,
  LeadCard,
  ProfileCatalog,
  ProviderCatalog,
  ResearchContract,
  RunSnapshot,
  SearchPayload,
  SegmentCatalog,
} from './types'

const API_BASE = import.meta.env.VITE_LEADFLOW_API ?? 'http://127.0.0.1:8765/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.detail ?? body
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message ?? `LeadFlow API respondeu ${response.status}`
    throw new ApiError(message, response.status, detail)
  }
  return body as T
}

export const api = {
  health: () => request<Health>('/health'),
  segments: () => request<SegmentCatalog>('/catalog/segments'),
  profiles: () => request<ProfileCatalog>('/catalog/profiles'),
  providers: () => request<ProviderCatalog>('/catalog/providers'),
  startRun: (payload: SearchPayload) =>
    request<RunSnapshot>('/runs', { method: 'POST', body: JSON.stringify(payload) }),
  getRun: (runId: string) => request<RunSnapshot>(`/runs/${runId}`),
  getResult: async (runId: string) => {
    const response = await request<{ id: string; status: string; result: ResearchContract | null }>(
      `/runs/${runId}/result`,
    )
    return response.result
  },
  cancelRun: (runId: string) => request<RunSnapshot>(`/runs/${runId}/cancel`, { method: 'POST' }),
  listLeads: (status: LifecycleStatus | "all" = "all") => request<LibraryResponse>(`/leads?status_filter=${encodeURIComponent(status)}`),
  getQueue: () => request<QueueResponse>(`/queue`),
  updateLifecycle: (leadKey: string, status: LifecycleStatus, note = "") => request<{ lead: LeadCard }>(`/leads/${encodeURIComponent(leadKey)}/lifecycle`, { method: "POST", body: JSON.stringify({ status, note }) }),
  enqueue: (leadKey: string, message?: string) => request<{ lead_key: string; status: string; lead: LeadCard }>(`/leads/${encodeURIComponent(leadKey)}/queue`, { method: "POST", body: JSON.stringify({ message: message || null }) }),
  settings: () => request<{ settings: LeadFlowSettings }>('/settings'),
  updateSettings: (settings: LeadFlowSettings) => request<{ settings: LeadFlowSettings }>('/settings', { method: 'PUT', body: JSON.stringify(settings) }),
  followUps: (dueOnly = false) => request<FollowUpResponse>(`/follow-ups?due_only=${dueOnly}`),
  scheduleFollowUp: (leadKey: string, followUpAt: string, note = '') => request<{ lead: LeadCard }>(`/leads/${encodeURIComponent(leadKey)}/follow-up`, { method: 'POST', body: JSON.stringify({ follow_up_at: followUpAt, note }) }),
  clearFollowUp: (leadKey: string) => request<{ lead: LeadCard }>(`/leads/${encodeURIComponent(leadKey)}/follow-up`, { method: 'DELETE' }),
  interactions: (leadKey: string) => request<InteractionResponse>(`/leads/${encodeURIComponent(leadKey)}/interactions`),
  addInteraction: (leadKey: string, payload: { kind?: string; channel?: string; outcome?: string; note?: string; status?: LifecycleStatus }) => request(`/leads/${encodeURIComponent(leadKey)}/interactions`, { method: 'POST', body: JSON.stringify(payload) }),
  prepareContact: (lead: LeadCard, message?: string) =>
    request<ContactPreparation>('/contact/prepare', {
      method: 'POST',
      body: JSON.stringify({ lead, message: message || null }),
    }),
}
