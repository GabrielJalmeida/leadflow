const OPPORTUNITY_LABELS: Record<string, string> = {
  new_site: 'Novo site',
  rebuild: 'Reconstrução',
  redesign: 'Redesign',
  optimization: 'Otimização',
  review_needed: 'Revisar',
  low_opportunity: 'Baixa oportunidade',
  unknown: 'Não definida',
}

const SERVICE_FIT_LABELS: Record<string, string> = {
  new_website: 'Novo site',
  website_rebuild: 'Reconstrução do site',
  website_redesign: 'Redesign do site',
  website_optimization: 'Otimização do site',
  website_review: 'Revisão do site',
  visual_review: 'Revisão visual',
  investigate_first: 'Investigar primeiro',
  do_not_contact: 'Não contatar',
  unknown: 'Revisar oportunidade',
}

const IDENTITY_LABELS: Record<string, string> = {
  matched: 'Correspondência confirmada',
  probable_match: 'Correspondência provável',
  unverified: 'Não verificada',
  ambiguous: 'Ambígua',
  mismatch: 'Incompatível',
  unknown: 'Não verificada',
}

const RUN_STATUS_LABELS: Record<string, string> = {
  queued: 'Na fila',
  running: 'Pesquisando',
  cancelling: 'Cancelando',
  completed: 'Concluída',
  partial_budget: 'Parcial · limite atingido',
  partial_results: 'Parcial',
  cancelled: 'Cancelada',
  failed: 'Falhou',
}

const PROFILE_LABELS: Record<string, string> = {
  balanced: 'Equilibrado',
  'website-sales': 'Venda de sites',
  'new-site': 'Novo site',
  redesign: 'Redesign',
  'visual-redesign': 'Redesign visual',
  'ready-only': 'Somente prontos',
  'instagram-first': 'Instagram primeiro',
  'phone-first': 'Celular primeiro',
}

export function opportunityLabel(value?: string) {
  return OPPORTUNITY_LABELS[value || 'unknown'] || value || 'Não definida'
}

export function serviceFitLabel(value?: string) {
  return SERVICE_FIT_LABELS[value || 'unknown'] || value?.replaceAll('_', ' ') || 'Revisar oportunidade'
}

export function identityLabel(value?: string) {
  return IDENTITY_LABELS[value || 'unknown'] || value?.replaceAll('_', ' ') || 'Não verificada'
}

export function readinessLabel(actionable?: boolean) {
  return actionable ? 'PRONTO' : 'VERIFICAR'
}

export function runStatusLabel(value?: string) {
  return RUN_STATUS_LABELS[value || ''] || value?.replaceAll('_', ' ') || '—'
}

export function profileLabel(slug: string, fallback?: string) {
  return PROFILE_LABELS[slug] || fallback || slug
}

export function providerLabel(value?: string | null) {
  if (!value) return 'Provedor'
  const labels: Record<string, string> = {
    auto: 'Automático',
    tavily: 'Tavily',
    brave: 'Brave',
    outscraper: 'Outscraper',
    gemini: 'Gemini',
  }
  return labels[value.toLowerCase()] || value
}
