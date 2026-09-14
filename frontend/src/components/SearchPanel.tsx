import { useMemo, useState } from 'react'
import {
  ChevronDownRegular,
  SearchRegular,
  StopRegular,
} from '@fluentui/react-icons'
import type {
  Health,
  ProfileCatalog,
  ProviderCatalog,
  SearchPayload,
  SegmentCatalog,
} from '../lib/types'
import { profileLabel, providerLabel } from '../lib/ptBR'

export type SearchFormValue = SearchPayload

const defaultValue: SearchFormValue = {
  segment: 'marcenaria',
  city: 'Praia Grande',
  state: 'SP',
  country: 'Brazil',
  limit: 10,
  max_queries: 20,
  profile: 'website-sales',
  provider: 'auto',
  no_ai: false,
  require_phone: false,
  filter_pool_multiplier: 5,
  contact_strategy: 'digital-first',
  fulfill_quota: true,
  raw_discovery: false,
  use_cache: true,
  refresh_cache: false,
  cache_ttl_days: 14,
  use_memory: true,
  filters: {
    website: 'any',
    instagram: 'any',
    phone: 'any',
    email: 'any',
    readiness: 'any',
    require_any_contact: false,
  },
  features: {
    investigate: true,
    investigation_limit: 3,
    investigation_budget: 2,
    audit_websites: true,
    audit_limit: 3,
    audit_timeout: 8,
    browser_audit: false,
    browser_audit_limit: 3,
    browser_timeout: 12,
    visual_audit: false,
    visual_audit_limit: 3,
  },
  budgets: {
    max_search_calls: 30,
    max_llm_calls: 30,
    max_website_audits: 25,
    max_browser_audits: 10,
    max_visual_audits: 10,
  },
}

type Props = {
  segments?: SegmentCatalog
  profiles?: ProfileCatalog
  providers?: ProviderCatalog
  health?: Health
  running: boolean
  onSearch: (payload: SearchPayload) => void
  onCancel: () => void
}

export function SearchPanel({ segments, profiles, providers, health, running, onSearch, onCancel }: Props) {
  const [value, setValue] = useState<SearchFormValue>(defaultValue)
  const [advanced, setAdvanced] = useState(false)

  const allSegments = useMemo(
    () => segments?.groups.flatMap((group) => group.items) ?? [],
    [segments],
  )

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!value.segment.trim() || !value.city.trim() || running) return
    onSearch({ ...value, segment: value.segment.trim(), city: value.city.trim(), state: value.state.trim() })
  }

  const providerOptions = [
    { slug: 'auto', label: 'Automático' },
    ...(providers?.items ?? []).filter((item) => item.slug !== 'gemini'),
  ]

  return (
    <form className="search-panel" onSubmit={submit}>
      <div className="search-panel__heading">
        <div>
          <p className="eyebrow">Área de descoberta</p>
          <h1>Encontre a próxima oportunidade.</h1>
        </div>
        <div className="research-mode" aria-label="Modo de pesquisa">
          <span>Núcleo de inteligência</span>
          <strong>{health?.configured.gemini ? 'Gemini ativo' : 'Modo básico'}</strong>
        </div>
      </div>

      <div className="search-grid">
        <label className="field field--wide">
          <span>Segmento</span>
          <input
            list="segments"
            value={value.segment}
            onChange={(event) => setValue({ ...value, segment: event.target.value })}
            placeholder="Ex.: marcenaria, vidraçaria, clínica..."
          />
          <datalist id="segments">
            {allSegments.map((item) => (
              <option key={item.slug} value={item.label} />
            ))}
          </datalist>
        </label>

        <label className="field field--wide">
          <span>Cidade</span>
          <input value={value.city} onChange={(event) => setValue({ ...value, city: event.target.value })} />
        </label>

        <label className="field field--state">
          <span>UF</span>
          <input
            value={value.state}
            maxLength={3}
            onChange={(event) => setValue({ ...value, state: event.target.value.toUpperCase() })}
          />
        </label>

        <label className="field field--count">
          <span>Quantidade</span>
          <input
            type="number"
            min={1}
            max={100}
            value={value.limit}
            onChange={(event) => setValue({ ...value, limit: Number(event.target.value) || 1 })}
          />
        </label>

        <label className="field">
          <span>Perfil</span>
          <select value={value.profile} onChange={(event) => setValue({ ...value, profile: event.target.value })}>
            {(profiles?.items ?? []).map((item) => (
              <option key={item.slug} value={item.slug}>{profileLabel(item.slug, item.label)}</option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Provedor</span>
          <select
            value={value.provider}
            onChange={(event) => setValue({ ...value, provider: event.target.value as SearchPayload['provider'] })}
          >
            {providerOptions.map((item) => {
              const configured = item.slug === 'auto' || ('configured' in item && item.configured)
              return (
                <option key={item.slug} value={item.slug} disabled={!configured}>
                  {providerLabel(item.slug)}{configured ? '' : ' · não configurado'}
                </option>
              )
            })}
          </select>
        </label>
      </div>

      <div className="research-mode-switch">
        <div>
          <span className="eyebrow">Modo de pesquisa</span>
          <strong>{value.raw_discovery ? 'Leads brutos' : 'Leads qualificados'}</strong>
          <p>{value.raw_discovery ? 'Mostra candidatos do segmento sem aplicar os filtros comerciais do perfil. A avaliação fica por sua conta.' : 'Aplica os filtros e etapas de qualificação do perfil selecionado.'}</p>
        </div>
        <label className="toggle-control">
          <input
            type="checkbox"
            checked={Boolean(value.raw_discovery)}
            onChange={(event) => setValue({ ...value, raw_discovery: event.target.checked })}
          />
          <span>Modo livre / sem filtros</span>
        </label>
      </div>

      <div className="quick-options">
        <label className="check-control">
          <input
            type="checkbox"
            checked={value.features.investigate}
            onChange={(event) => setValue({ ...value, features: { ...value.features, investigate: event.target.checked } })}
          />
          <span>Investigar</span>
        </label>
        <label className="check-control">
          <input
            type="checkbox"
            checked={value.features.audit_websites}
            onChange={(event) => setValue({ ...value, features: { ...value.features, audit_websites: event.target.checked } })}
          />
          <span>Auditar sites</span>
        </label>
        <label className="check-control">
          <input
            type="checkbox"
            checked={value.features.browser_audit}
            onChange={(event) => setValue({ ...value, features: { ...value.features, browser_audit: event.target.checked } })}
          />
          <span>Navegador / experiência</span>
        </label>
        <label className="check-control">
          <input
            type="checkbox"
            checked={value.features.visual_audit}
            disabled={!health?.configured.gemini}
            onChange={(event) => setValue({ ...value, features: { ...value.features, visual_audit: event.target.checked } })}
          />
          <span>Visual por IA</span>
        </label>
      </div>

      <div className={`advanced-panel ${advanced ? 'is-open' : ''} ${value.raw_discovery ? 'is-disabled' : ''}`}>
        <button className="advanced-toggle" type="button" onClick={() => setAdvanced((current) => !current)}>
          <ChevronDownRegular aria-hidden="true" />
          Filtros avançados{value.raw_discovery ? ' · desativados no modo livre' : ''}
        </button>
        {advanced && (
          <div className="advanced-grid">
            <label className="field"><span>Site</span><select value={value.filters.website} onChange={(e) => setValue({ ...value, filters: { ...value.filters, website: e.target.value as NonNullable<SearchPayload['filters']['website']> } })}><option value="any">Qualquer</option><option value="not_found">Sem site verificado</option><option value="present">Com site</option><option value="unknown">Desconhecido</option><option value="unreachable">Inacessível</option></select></label>
            <label className="field"><span>Instagram</span><select value={value.filters.instagram} onChange={(e) => setValue({ ...value, filters: { ...value.filters, instagram: e.target.value as NonNullable<SearchPayload['filters']['instagram']> } })}><option value="any">Qualquer</option><option value="present">Presente</option><option value="missing">Ausente</option></select></label>
            <label className="field"><span>Celular</span><select value={value.filters.phone} onChange={(e) => setValue({ ...value, filters: { ...value.filters, phone: e.target.value as NonNullable<SearchPayload['filters']['phone']> } })}><option value="any">Qualquer</option><option value="present">Presente</option><option value="missing">Ausente</option></select></label>
            <label className="field"><span>Prontidão</span><select value={value.filters.readiness} onChange={(e) => setValue({ ...value, filters: { ...value.filters, readiness: e.target.value as NonNullable<SearchPayload['filters']['readiness']> } })}><option value="any">PRONTO + VERIFICAR</option><option value="ready">PRONTO</option><option value="verify">VERIFICAR</option></select></label>
            <label className="field"><span>Potencial mínimo</span><input type="number" min={0} max={100} value={value.filters.min_opportunity_score ?? ''} placeholder="0–100" onChange={(e) => setValue({ ...value, filters: { ...value.filters, min_opportunity_score: e.target.value ? Number(e.target.value) : undefined } })} /></label>
            <label className="field"><span>Amplitude da busca</span><select value={value.filter_pool_multiplier} onChange={(e) => setValue({ ...value, filter_pool_multiplier: Number(e.target.value) })}><option value={1}>1×</option><option value={2}>2×</option><option value={3}>3×</option><option value={4}>4×</option><option value={5}>5×</option><option value={6}>6×</option><option value={7}>7×</option><option value={8}>8×</option></select></label>
          </div>
        )}
      </div>

      <div className="search-actions">
        <p className="search-hint">No modo qualificado, a busca respeita os critérios de qualidade. No modo livre, você recebe candidatos para avaliar manualmente.</p>
        {running ? (
          <button className="button button--quiet" type="button" onClick={onCancel}>
            <StopRegular aria-hidden="true" /> Cancelar
          </button>
        ) : (
          <button className="button button--primary" type="submit">
            <SearchRegular aria-hidden="true" /> Buscar oportunidades
          </button>
        )}
      </div>
    </form>
  )
}
