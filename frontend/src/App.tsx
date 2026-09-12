import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowSyncRegular,
  CloudCheckmarkRegular,
  ErrorCircleRegular,
  SearchRegular,
} from '@fluentui/react-icons'
import { api } from './lib/api'
import type { RunSnapshot, SearchPayload } from './lib/types'
import { providerLabel, runStatusLabel } from './lib/ptBR'
import { NavRail } from './components/NavRail'
import { SearchPanel } from './components/SearchPanel'
import { LeadTable } from './components/LeadTable'
import { LeadInspector } from './components/LeadInspector'
import { StatusDot } from './components/StatusDot'
import { useWorkspaceStore } from './store/useWorkspaceStore'

const terminal = new Set(['completed', 'partial_budget', 'partial_results', 'cancelled', 'failed'])

function App() {
  const [run, setRun] = useState<RunSnapshot | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const { result, selectedLead, setResult, setSelectedLead, reset } = useWorkspaceStore()

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const segments = useQuery({ queryKey: ['segments'], queryFn: api.segments, enabled: health.isSuccess })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.profiles, enabled: health.isSuccess })
  const providers = useQuery({ queryKey: ['providers'], queryFn: api.providers, enabled: health.isSuccess })

  const start = useMutation({
    mutationFn: api.startRun,
    onSuccess: (snapshot) => {
      setLastError(null)
      reset()
      setRun(snapshot)
    },
    onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível iniciar a busca.'),
  })

  const statusQuery = useQuery({
    queryKey: ['run', run?.id],
    queryFn: () => api.getRun(run!.id),
    enabled: Boolean(run?.id && !terminal.has(run.status)),
    refetchInterval: 650,
  })

  useEffect(() => {
    if (statusQuery.data) setRun(statusQuery.data)
  }, [statusQuery.data])

  const resultQuery = useQuery({
    queryKey: ['run-result', run?.id],
    queryFn: () => api.getResult(run!.id),
    enabled: Boolean(run?.id && terminal.has(run.status) && run.status !== 'failed'),
    retry: 2,
  })

  useEffect(() => {
    if (resultQuery.data) setResult(resultQuery.data)
  }, [resultQuery.data, setResult])

  useEffect(() => {
    if (run?.status === 'failed') {
      setLastError(run.error?.message || 'A pesquisa falhou.')
    }
  }, [run])

  const cancel = useMutation({
    mutationFn: () => api.cancelRun(run!.id),
    onSuccess: setRun,
    onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível cancelar.'),
  })

  const isRunning = Boolean(run && !terminal.has(run.status))
  const apiOnline = health.isSuccess
  const returned = result?.run?.returned_results ?? result?.leads?.length ?? 0
  const requested = result?.run?.requested_results ?? 0
  const usage = result?.run?.usage
  const quotaPartial = Boolean(result && result.run.quota_fulfilled === false && requested > returned)

  const providerSummary = useMemo(() => {
    const configured = health.data?.configured
    if (!configured) return '—'
    const names = Object.entries(configured)
      .filter(([, value]) => value)
      .map(([name]) => providerLabel(name))
    return names.length ? names.join(' · ') : 'nenhum provedor'
  }, [health.data])

  function startSearch(payload: SearchPayload) {
    setRun(null)
    setResult(null)
    start.mutate(payload)
  }

  return (
    <div className="app-stage">
      <div className="ambient ambient--one" aria-hidden="true" />
      <div className="ambient ambient--two" aria-hidden="true" />
      <div className="app-shell">
        <NavRail />
        <main className="workspace">
          <header className="topbar">
            <div className="topbar__context">
              <span className="workspace-label">LeadFlow</span>
              <span className="topbar-divider" />
              <span>Descobrir</span>
            </div>
            <div className="topbar__status">
              {apiOnline ? <StatusDot tone="online" label="API local" /> : <StatusDot tone="offline" label="API indisponível" />}
              <span className="configured-providers">{providerSummary}</span>
            </div>
          </header>

          <div className="workspace-body">
            <section className="primary-pane">
              <SearchPanel
                segments={segments.data}
                profiles={profiles.data}
                providers={providers.data}
                health={health.data}
                running={isRunning || start.isPending}
                onSearch={startSearch}
                onCancel={() => run && cancel.mutate()}
              />

              {isRunning && (
                <div className="run-banner" role="status" aria-live="polite">
                  <div className="run-banner__signal"><span /><span /><span /></div>
                  <div><strong>Pesquisa em andamento</strong><span>{run?.status === 'cancelling' ? 'Finalizando com segurança…' : 'LeadFlow está descobrindo e qualificando oportunidades.'}</span></div>
                  <div className="run-banner__id">{run?.id.slice(0, 8)}</div>
                </div>
              )}

              {lastError && (
                <div className="message-bar message-bar--error" role="alert">
                  <ErrorCircleRegular />
                  <div><strong>Não foi possível concluir a operação.</strong><span>{lastError}</span></div>
                  <button className="icon-button" onClick={() => setLastError(null)} aria-label="Dispensar erro">×</button>
                </div>
              )}

              {quotaPartial && (
                <div className="message-bar message-bar--warning" role="status">
                  <ErrorCircleRegular />
                  <div>
                    <strong>Quantidade parcial de oportunidades.</strong>
                    <span>
                      Encontramos {returned} de {requested}. O LeadFlow tentou ampliar a descoberta sem reduzir os critérios de qualidade
                      {usage?.search_calls ? ` e utilizou ${usage.search_calls} buscas.` : '.'}
                    </span>
                  </div>
                </div>
              )}

              <section className="results-surface">
                <div className="results-toolbar">
                  <div>
                    <p className="eyebrow">Fluxo de oportunidades</p>
                    <h2>{result ? `${returned} empresas encontradas` : 'Resultados'}</h2>
                  </div>
                  {result && (
                    <div className="results-summary">
                      <span>{returned}/{requested || returned}</span>
                      <span>{providerLabel(run?.provider)}</span>
                      <span className={`run-state run-state--${result.run.status}`}>{runStatusLabel(result.run.status)}</span>
                    </div>
                  )}
                </div>

                {!apiOnline && health.isError ? (
                  <div className="empty-state">
                    <CloudCheckmarkRegular />
                    <h3>Inicie a API local</h3>
                    <p>Abra outro terminal na raiz do projeto e execute <code>leadflow api</code>.</p>
                    <button className="button button--quiet" onClick={() => health.refetch()}><ArrowSyncRegular /> Tentar novamente</button>
                  </div>
                ) : !result ? (
                  <div className="empty-state empty-state--quiet">
                    <div className="empty-signal"><SearchRegular /></div>
                    <h3>Sua próxima oportunidade ainda não está aqui.</h3>
                    <p>Defina segmento e localização. Os resultados qualificados aparecem nesta área sem tirar você do contexto.</p>
                  </div>
                ) : result.leads.length === 0 ? (
                  <div className="empty-state"><SearchRegular /><h3>Nenhuma oportunidade elegível</h3><p>A pesquisa terminou sem resultados que passassem pelos critérios atuais. Ajuste os filtros ou amplie a busca.</p></div>
                ) : (
                  <LeadTable leads={result.leads} selected={selectedLead} onSelect={setSelectedLead} />
                )}
              </section>
            </section>

            {selectedLead && <LeadInspector lead={selectedLead} onClose={() => setSelectedLead(null)} />}
          </div>

          <footer className="statusbar">
            <div><StatusDot tone={apiOnline ? 'online' : 'offline'} label={apiOnline ? 'Núcleo conectado' : 'Núcleo desconectado'} /><span>Contrato {health.data?.frontend_contract_version ?? '—'}</span></div>
            <div>
              {usage && <span>Buscas {usage.search_calls ?? 0} · IA {usage.llm_calls ?? 0} · HTTP {usage.website_audits ?? 0} · Navegador {usage.browser_audits ?? 0} · Visual {usage.visual_audits ?? 0}</span>}
              <span>LeadFlow alfa</span>
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}

export default App
