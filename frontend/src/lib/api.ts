import type {
  ContactPreparation,
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
  prepareContact: (lead: LeadCard, message?: string) =>
    request<ContactPreparation>('/contact/prepare', {
      method: 'POST',
      body: JSON.stringify({ lead, message: message || null }),
    }),
}
