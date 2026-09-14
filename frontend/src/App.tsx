import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowSyncRegular, CloudCheckmarkRegular, ErrorCircleRegular, SearchRegular, SendRegular, OpenRegular, DismissRegular } from '@fluentui/react-icons'
import { api } from './lib/api'
import type { LeadCard, LeadFlowSettings, LifecycleStatus, RunSnapshot, SearchPayload } from './lib/types'
import { providerLabel, runStatusLabel } from './lib/ptBR'
import { NavRail } from './components/NavRail'
import { SearchPanel } from './components/SearchPanel'
import { LeadTable } from './components/LeadTable'
import { LeadInspector } from './components/LeadInspector'
import { SettingsPanel } from './components/SettingsPanel'
import { StatusDot } from './components/StatusDot'
import { useWorkspaceStore } from './store/useWorkspaceStore'

type View = 'discover' | 'pipeline' | 'queue' | 'followups' | 'contacted' | 'ignored' | 'accepted' | 'hidden' | 'settings'
const terminal = new Set(['completed', 'partial_budget', 'partial_results', 'cancelled', 'failed'])

const viewLabels: Record<View, string> = {
  pipeline: 'Pipeline',
  discover: 'Descobrir', queue: 'Fila de contato', followups: 'Follow-ups', contacted: 'Contactados', ignored: 'Ignorados', accepted: 'Aceitos', hidden: 'Escondidos', settings: 'Configurações',
}

function App() {
  const [view, setView] = useState<View>('discover')
  const [run, setRun] = useState<RunSnapshot | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchMessage, setBatchMessage] = useState<string | null>(null)
  const [operatorIndex, setOperatorIndex] = useState(0)
  const [operatorBusy, setOperatorBusy] = useState(false)
  const [operatorMessage, setOperatorMessage] = useState<string | null>(null)
  const { result, selectedLead, setResult, setSelectedLead, reset } = useWorkspaceStore()
  const queryClient = useQueryClient()

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const segments = useQuery({ queryKey: ['segments'], queryFn: api.segments, enabled: health.isSuccess })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: api.profiles, enabled: health.isSuccess })
  const providers = useQuery({ queryKey: ['providers'], queryFn: api.providers, enabled: health.isSuccess })
  const followUps = useQuery({ queryKey: ['follow-ups'], queryFn: () => api.followUps(false), enabled: health.isSuccess && view === 'followups', refetchInterval: 30000 })
  const libraryStatus = view === 'ignored' ? 'ignored' : view === 'accepted' ? 'accepted' : view === 'hidden' ? 'hidden' : view === 'contacted' ? 'contacted' : 'all'
  const library = useQuery({ queryKey: ['leads', libraryStatus], queryFn: () => api.listLeads(libraryStatus), enabled: health.isSuccess && view !== 'discover' && view !== 'queue' && view !== 'settings' })
  const queue = useQuery({ queryKey: ['queue'], queryFn: api.getQueue, enabled: health.isSuccess && view === 'queue', refetchInterval: 5000 })
  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: api.settings, enabled: health.isSuccess && view === 'settings', staleTime: 5 * 60 * 1000, retry: 1 })
  const settingsMutation = useMutation({ mutationFn: api.updateSettings, onSuccess: (response) => { queryClient.setQueryData(['settings'], response) }, onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível salvar as configurações.') })

  const start = useMutation({
    mutationFn: api.startRun,
    onSuccess: (snapshot) => { setLastError(null); reset(); setRun(snapshot) },
    onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível iniciar a busca.'),
  })
  const statusQuery = useQuery({ queryKey: ['run', run?.id], queryFn: () => api.getRun(run!.id), enabled: Boolean(run?.id && !terminal.has(run.status)), refetchInterval: 650 })
  useEffect(() => { if (statusQuery.data) setRun(statusQuery.data) }, [statusQuery.data])
  const resultQuery = useQuery({ queryKey: ['run-result', run?.id], queryFn: () => api.getResult(run!.id), enabled: Boolean(run?.id && terminal.has(run.status) && run.status !== 'failed'), retry: 2 })
  useEffect(() => { if (resultQuery.data) setResult(resultQuery.data) }, [resultQuery.data, setResult])
  useEffect(() => { if (run?.status === 'failed') setLastError(run.error?.message || 'A pesquisa falhou.') }, [run])

  const cancel = useMutation({ mutationFn: () => api.cancelRun(run!.id), onSuccess: setRun, onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível cancelar.') })
  const lifecycleMutation = useMutation({
    mutationFn: ({ lead, status }: { lead: LeadCard; status: LifecycleStatus }) => api.updateLifecycle(lead.lead_key!, status),
    onSuccess: ({ lead }) => {
      setSelectedLead(lead)
      queryClient.invalidateQueries({ queryKey: ['leads'] })
      queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível atualizar o lead.'),
  })
  const enqueueMutation = useMutation({
    mutationFn: ({ lead, message }: { lead: LeadCard; message?: string }) => api.enqueue(lead.lead_key!, message),
    onSuccess: (item: any) => { setSelectedLead(item.lead); queryClient.invalidateQueries({ queryKey: ['queue'] }); queryClient.invalidateQueries({ queryKey: ['leads'] }) },
    onError: (error) => setLastError(error instanceof Error ? error.message : 'Não foi possível adicionar à fila.'),
  })

  const isRunning = Boolean(run && !terminal.has(run.status))
  const apiOnline = health.isSuccess
  const returned = result?.run?.returned_results ?? result?.leads?.length ?? 0
  const requested = result?.run?.requested_results ?? 0
  const usage = result?.run?.usage
  const quotaPartial = Boolean(result && result.run.quota_fulfilled === false && requested > returned)
  const discovery = result?.run?.discovery
  const quality = result?.run?.quality
  const providerSummary = useMemo(() => {
    const configured = health.data?.configured
    if (!configured) return '—'
    const names = Object.entries(configured).filter(([, value]) => value).map(([name]) => providerLabel(name))
    return names.length ? names.join(' · ') : 'nenhum provedor'
  }, [health.data])

  function startSearch(payload: SearchPayload) {
    setView('discover')
    setRun(null)
    setResult(null)
    setSelectedKeys(new Set())
    setBatchMessage(null)
    start.mutate({ ...payload, exclude_existing_leads: true })
  }

  useEffect(() => {
    setSelectedKeys(new Set())
    setBatchMessage(null)
    setOperatorMessage(null)
    setOperatorIndex(0)
  }, [view])

  const displayLeads = view === 'discover' ? (result?.leads ?? []) : view === 'queue' ? (queue.data?.items.map(item => item.lead) ?? []) : view === 'followups' ? (followUps.data?.items.map(item => item.lead) ?? []) : view === 'settings' ? [] : (library.data?.leads ?? [])
  const operatorItems = queue.data?.items ?? []
  const operatorItem = operatorItems[operatorIndex] ?? null
  const pipelineColumns: Array<{ status: LifecycleStatus; label: string }> = [
    { status: 'accepted', label: 'Aceitos' },
    { status: 'contacted', label: 'Contactados' },
    { status: 'awaiting_response', label: 'Aguardando resposta' },
    { status: 'responded', label: 'Respondeu' },
    { status: 'proposal_sent', label: 'Proposta enviada' },
    { status: 'negotiating', label: 'Negociando' },
    { status: 'won', label: 'Ganhos' },
    { status: 'lost', label: 'Perdidos' },
  ]

  useEffect(() => {
    if (operatorItems.length === 0) { setOperatorIndex(0); return }
    setOperatorIndex((current) => Math.min(current, operatorItems.length - 1))
  }, [operatorItems.length])
  const selectedLeads = displayLeads.filter((lead) => lead.lead_key && selectedKeys.has(lead.lead_key))

  function toggleSelection(lead: LeadCard, checked: boolean) {
    if (!lead.lead_key) return
    setSelectedKeys((current) => {
      const next = new Set(current)
      if (checked) next.add(lead.lead_key!)
      else next.delete(lead.lead_key!)
      return next
    })
  }

  function toggleAll(checked: boolean) {
    setSelectedKeys((current) => {
      const next = new Set(current)
      displayLeads.forEach((lead) => {
        if (!lead.lead_key) return
        if (checked) next.add(lead.lead_key)
        else next.delete(lead.lead_key)
      })
      return next
    })
  }

  async function queueSelected() {
    if (!selectedLeads.length || batchBusy) return
    setBatchBusy(true)
    setBatchMessage(null)
    try {
      const results = await Promise.allSettled(selectedLeads.map((lead) => api.enqueue(lead.lead_key!, undefined)))
      const ok = results.filter((item) => item.status === 'fulfilled').length
      const failed = results.length - ok
      setBatchMessage(`${ok} lead${ok === 1 ? '' : 's'} colocado${ok === 1 ? '' : 's'} na fila${failed ? ` · ${failed} falha${failed === 1 ? '' : 's'}` : ''}.`)
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      queryClient.invalidateQueries({ queryKey: ['leads'] })
      setSelectedKeys(new Set())
    } finally {
      setBatchBusy(false)
    }
  }

  async function openSelectedBatch() {
    if (!selectedLeads.length || batchBusy) return
    setBatchBusy(true)
    setBatchMessage(null)
    const windows = selectedLeads.map((lead) => ({ lead, window: window.open('', '_blank') }))
    try {
      const results = await Promise.allSettled(windows.map(async ({ lead, window: popup }) => {
        const prepared = await api.prepareContact(lead)
        const url = prepared.channel === 'instagram' ? prepared.instagram_url : prepared.whatsapp_url
        if (popup && url) {
          popup.location.href = url
          return true
        }
        if (popup && !url) popup.close()
        return false
      }))
      const opened = results.filter((item) => item.status === 'fulfilled' && item.value).length
      const blocked = results.length - opened
      setBatchMessage(`${opened} contato${opened === 1 ? '' : 's'} aberto${opened === 1 ? '' : 's'} em lote${blocked ? ` · ${blocked} sem rota ou bloqueado` : ''}. O envio continua manual.`)
    } finally {
      setBatchBusy(false)
    }
  }


  async function openOperatorContact() {
    if (!operatorItem || operatorBusy) return
    setOperatorBusy(true)
    setOperatorMessage(null)
    try {
      const prepared = await api.prepareContact(operatorItem.lead, operatorItem.message || undefined)
      const url = prepared.channel === 'instagram' ? prepared.instagram_url : prepared.whatsapp_url
      if (!url) {
        setOperatorMessage('Este lead não possui uma rota de contato disponível.')
        return
      }
      try { await navigator.clipboard.writeText(prepared.message) } catch { /* clipboard is optional */ }
      window.open(url, '_blank', 'noopener,noreferrer')
      setOperatorMessage('Contato aberto. A mensagem foi copiada quando o navegador permitiu.')
    } catch (error) {
      setLastError(error instanceof Error ? error.message : 'Não foi possível preparar o contato.')
    } finally {
      setOperatorBusy(false)
    }
  }

  async function finishOperator(status: LifecycleStatus) {
    if (!operatorItem || operatorBusy || !operatorItem.lead.lead_key) return
    setOperatorBusy(true)
    setOperatorMessage(null)
    try {
      await api.updateLifecycle(operatorItem.lead.lead_key, status)
      await queryClient.invalidateQueries({ queryKey: ['queue'] })
      await queryClient.invalidateQueries({ queryKey: ['leads'] })
      setOperatorIndex((current) => Math.max(0, Math.min(current, operatorItems.length - 2)))
      setOperatorMessage(status === 'contacted' ? 'Lead marcado como contactado. Avançando.' : 'Lead retirado da fila. Avançando.')
    } catch (error) {
      setLastError(error instanceof Error ? error.message : 'Não foi possível atualizar o lead.')
    } finally {
      setOperatorBusy(false)
    }
  }


  return (
    <div className="app-stage"><div className="ambient ambient--one" aria-hidden="true" /><div className="ambient ambient--two" aria-hidden="true" />
      <div className="app-shell">
        <NavRail view={view} onView={setView} />
        <main className="workspace">
          <header className="topbar"><div className="topbar__context"><span className="workspace-label">LeadFlow</span><span className="topbar-divider" /><span>{viewLabels[view]}</span></div><div className="topbar__status">{apiOnline ? <StatusDot tone="online" label="API local" /> : <StatusDot tone="offline" label="API indisponível" />}<span className="configured-providers">{providerSummary}</span></div></header>
          <div className="workspace-body">
            <section className="primary-pane">
              {view === 'discover' && <SearchPanel segments={segments.data} profiles={profiles.data} providers={providers.data} health={health.data} running={isRunning || start.isPending} onSearch={startSearch} onCancel={() => run && cancel.mutate()} />}
              {view === 'discover' && isRunning && <div className="run-banner" role="status" aria-live="polite"><div className="run-banner__signal"><span /><span /><span /></div><div><strong>Pesquisa em andamento</strong><span>{run?.status === 'cancelling' ? 'Finalizando com segurança…' : 'LeadFlow está descobrindo e qualificando oportunidades.'}</span></div><div className="run-banner__id">{run?.id.slice(0, 8)}</div></div>}
              {lastError && <div className="message-bar message-bar--error" role="alert"><ErrorCircleRegular /><div><strong>Não foi possível concluir a operação.</strong><span>{lastError}</span></div><button className="icon-button" onClick={() => setLastError(null)} aria-label="Dispensar erro">×</button></div>}
              {view === 'discover' && quotaPartial && <div className="message-bar message-bar--warning" role="status"><ErrorCircleRegular /><div><strong>Quantidade parcial de oportunidades.</strong><span>Encontramos {returned} de {requested}. Candidatos únicos: {discovery?.unique_candidates ?? '—'} · pré-qualificados: {discovery?.prequalified_candidates ?? '—'} · rejeitados no filtro: {quality?.filter_rejected ?? '—'}. {run?.status === 'partial_budget' ? 'O limite operacional encerrou a busca.' : 'O LeadFlow não encontrou candidatos suficientes que sobrevivessem aos critérios atuais.'}</span></div></div>}
              {view === 'settings' ? <SettingsPanel value={settingsQuery.data?.settings} saving={settingsMutation.isPending} onSave={(value: LeadFlowSettings) => settingsMutation.mutate(value)} /> : view === 'pipeline' ? <section className="results-surface"><div className="results-toolbar"><div><p className="eyebrow">Fluxo comercial</p><h2>Pipeline de vendas</h2></div><div className="results-summary"><span>{library.data?.count ?? 0} leads na base</span></div></div><div className="pipeline-grid">{pipelineColumns.map((column) => { const leads = (library.data?.leads ?? []).filter((lead) => lead.lifecycle?.status === column.status); return <div className="pipeline-column" key={column.status}><div className="pipeline-column__head"><strong>{column.label}</strong><span>{leads.length}</span></div>{leads.slice(0, 12).map((lead) => <button className="pipeline-card" type="button" key={lead.lead_key} onClick={() => setSelectedLead(lead)}><strong>{lead.name}</strong><span>{[lead.location?.city, lead.location?.state].filter(Boolean).join(' · ')}</span><small>Score {lead.opportunity?.score ?? 0}</small></button>)}{leads.length === 0 && <span className="pipeline-empty">Nenhum lead</span>}</div> })}</div></section> : <section className="results-surface">
                <div className="results-toolbar"><div><p className="eyebrow">{view === 'discover' ? 'Fluxo de oportunidades' : viewLabels[view]}</p><h2>{view === 'discover' ? (result ? `${returned} novas empresas encontradas` : 'Resultados') : view === 'followups' ? `${followUps.data?.count ?? 0} acompanhamentos` : `${displayLeads.length} leads`}</h2></div>{view === 'queue' && queue.data && <div className="results-summary"><span>{queue.data.count} na fila</span><span>Envio manual</span></div>}</div>
                {view === 'queue' && operatorItem && (
                  <div className="operator-card" aria-label="Modo operador da fila">
                    <div className="operator-card__head">
                      <div>
                        <p className="eyebrow">Modo operador</p>
                        <strong>{operatorIndex + 1} / {operatorItems.length}</strong>
                      </div>
                      <span>Envio manual · próximo lead automático</span>
                    </div>
                    <div className="operator-card__body">
                      <div className="operator-card__lead">
                        <strong>{operatorItem.lead.name}</strong>
                        <span>{[operatorItem.lead.location?.city, operatorItem.lead.location?.state].filter(Boolean).join(' · ') || 'Localidade não informada'}</span>
                        <span>{operatorItem.lead.contact?.phone || operatorItem.lead.contact?.email || 'Sem contato principal'}</span>
                      </div>
                      <div className="operator-card__actions">
                        <button className="button button--quiet" type="button" onClick={() => setOperatorIndex((current) => Math.max(0, current - 1))} disabled={operatorIndex === 0 || operatorBusy}>← Anterior</button>
                        <button className="button button--primary" type="button" onClick={openOperatorContact} disabled={operatorBusy}><OpenRegular /> Abrir contato</button>
                        <button className="button button--quiet" type="button" onClick={() => void finishOperator('contacted')} disabled={operatorBusy}>✓ Contactado e próximo</button>
                        <button className="button button--quiet" type="button" onClick={() => void finishOperator('ignored')} disabled={operatorBusy}>→ Pular</button>
                        <button className="button button--quiet" type="button" onClick={() => setOperatorIndex((current) => Math.min(operatorItems.length - 1, current + 1))} disabled={operatorIndex >= operatorItems.length - 1 || operatorBusy}>Próximo →</button>
                      </div>
                    </div>
                    {operatorMessage && <div className="operator-card__message" role="status">{operatorMessage}</div>}
                  </div>
                )}
                {displayLeads.length > 0 && (
                  <div className="batch-toolbar">
                    <span><strong>{selectedLeads.length}</strong> selecionados</span>
                    <div>
                      <button className="button button--quiet" type="button" onClick={() => setSelectedKeys(new Set())} disabled={!selectedLeads.length || batchBusy}><DismissRegular /> Limpar</button>
                      <button className="button button--quiet" type="button" onClick={queueSelected} disabled={!selectedLeads.length || batchBusy}><SendRegular /> {batchBusy ? 'Processando…' : 'Adicionar à fila'}</button>
                      <button className="button button--primary" type="button" onClick={openSelectedBatch} disabled={!selectedLeads.length || batchBusy}><OpenRegular /> Abrir lote</button>
                    </div>
                  </div>
                )}
                {batchMessage && <div className="batch-message" role="status">{batchMessage}</div>}
                {!apiOnline && health.isError ? <div className="empty-state"><CloudCheckmarkRegular /><h3>Inicie a API local</h3><p>Abra outro terminal na raiz do projeto e execute <code>leadflow api</code>.</p><button className="button button--quiet" onClick={() => health.refetch()}><ArrowSyncRegular /> Tentar novamente</button></div>
                : displayLeads.length === 0 ? <div className="empty-state"><div className="empty-signal"><SearchRegular /></div><h3>{view === 'discover' ? 'Sua próxima oportunidade ainda não está aqui.' : 'Nenhum lead nesta visão'}</h3><p>{view === 'discover' ? 'A próxima busca procura empresas que ainda não estão na sua biblioteca local.' : 'Leads mudam de visão conforme você os aceita, ignora, esconde, coloca na fila ou marca como contactado.'}</p></div>
                : <LeadTable leads={displayLeads} selected={selectedLead} selectedKeys={selectedKeys} onSelectionChange={toggleSelection} onToggleAll={toggleAll} onSelect={setSelectedLead} />}
              </section>}
            </section>
            {selectedLead && <LeadInspector lead={selectedLead} settings={settingsQuery.data?.settings} onClose={() => setSelectedLead(null)} onLifecycle={(lead, status) => lifecycleMutation.mutate({ lead, status })} onEnqueue={(lead, message) => enqueueMutation.mutate({ lead, message })} />}
          </div>
          <footer className="statusbar"><div><StatusDot tone={apiOnline ? 'online' : 'offline'} label={apiOnline ? 'Núcleo conectado' : 'Núcleo desconectado'} /><span>Contrato {health.data?.frontend_contract_version ?? '—'}</span></div><div>{usage && view === 'discover' && <span>Buscas {usage.search_calls ?? 0} · IA {usage.llm_calls ?? 0} · HTTP {usage.website_audits ?? 0} · Navegador {usage.browser_audits ?? 0} · Visual {usage.visual_audits ?? 0}</span>}<span>LeadFlow alfa</span></div></footer>
        </main>
      </div>
    </div>
  )
}

export default App
