export type RunStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'partial_budget'
  | 'partial_results'
  | 'cancelled'
  | 'failed'

export type Health = {
  status: string
  api_version: string
  frontend_contract_version: string
  configured: {
    gemini: boolean
    tavily: boolean
    brave: boolean
    outscraper: boolean
  }
}

export type SegmentCatalog = {
  groups: Array<{
    category: string
    items: Array<{ slug: string; label: string; aliases: string[] }>
  }>
  free_text_allowed: boolean
}

export type ProfileCatalog = {
  items: Array<{ slug: string; label: string; description: string }>
}

export type ProviderCatalog = {
  items: Array<{
    slug: string
    label: string
    roles: string[]
    capabilities: string[]
    byok: boolean
    configured: boolean
  }>
}

export type LeadCard = {
  name: string
  location: { city?: string; state?: string; country?: string }
  contact: { phone?: string | null; email?: string | null; socials?: string[] }
  website: {
    url?: string | null
    status?: string
    technical_score?: number | null
    browser_ux_score?: number | null
    visual_score?: number | null
  }
  identity: { status?: string; confidence?: number }
  opportunity: {
    score?: number
    type?: string
    actionable?: boolean
    service_fit?: string
    reasons?: string[]
    cautions?: string[]
  }
}

export type ResearchContract = {
  contract_version: string
  run: {
    status: string
    stop_reason?: string | null
    started_at?: string
    finished_at?: string
    requested_results?: number
    returned_results?: number
    quota_fulfilled?: boolean
    shortfall?: number
    usage?: {
      search_calls?: number
      llm_calls?: number
      website_audits?: number
      browser_audits?: number
      visual_audits?: number
    }
  }
  goal: { segment?: string; city?: string; state?: string; country?: string }
  leads: LeadCard[]
}

export type RunSnapshot = {
  id: string
  status: RunStatus
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  provider?: string | null
  db_run_id?: number | null
  error?: { code: string; message: string; retryable?: boolean } | null
}

export type SearchPayload = {
  segment: string
  city: string
  state: string
  country: string
  limit: number
  max_queries: number
  profile: string
  provider: 'auto' | 'tavily' | 'brave' | 'outscraper'
  no_ai: boolean
  require_phone: boolean
  filter_pool_multiplier: number
  contact_strategy: 'digital-first' | 'multichannel'
  fulfill_quota: boolean
  use_cache: boolean
  refresh_cache: boolean
  cache_ttl_days: number
  use_memory: boolean
  filters: {
    website?: 'any' | 'unknown' | 'present' | 'not_found' | 'unreachable'
    instagram?: 'any' | 'present' | 'missing'
    phone?: 'any' | 'present' | 'missing'
    email?: 'any' | 'present' | 'missing'
    readiness?: 'any' | 'ready' | 'verify'
    min_opportunity_score?: number
    require_any_contact: boolean
  }
  features: {
    investigate: boolean
    investigation_limit: number
    investigation_budget: number
    audit_websites: boolean
    audit_limit: number
    audit_timeout: number
    browser_audit: boolean
    browser_audit_limit: number
    browser_timeout: number
    visual_audit: boolean
    visual_audit_limit: number
  }
  budgets: {
    max_search_calls: number
    max_llm_calls: number
    max_website_audits: number
    max_browser_audits: number
    max_visual_audits: number
  }
}

export type ContactPreparation = {
  channel: 'whatsapp' | 'whatsapp_test' | 'instagram' | 'none'
  label: string
  message: string
  whatsapp_number?: string | null
  whatsapp_url?: string | null
  instagram_url?: string | null
  whatsapp_source?: string | null
}
