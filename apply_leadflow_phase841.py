from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
backups: dict[Path, str | None] = {}


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        raise RuntimeError(f"arquivo não encontrado: {rel}")
    return path.read_text(encoding="utf-8")


def backup(path: Path) -> None:
    if path not in backups:
        backups[path] = path.read_text(encoding="utf-8") if path.exists() else None


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 trecho compatível, encontrado {count}")
    return text.replace(old, new, 1)


def rollback() -> None:
    for path, original in reversed(list(backups.items())):
        if original is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(original, encoding="utf-8")


try:
    # Preflight: Phase 8.4 precisa estar presente.
    if "digital_contact_only" not in read("leadflow_agent/agent.py"):
        raise RuntimeError("Phase 8.4 não detectada em leadflow_agent/agent.py")
    if 'contact_strategy: str = "digital-first"' not in read("leadflow_agent/search_service.py"):
        raise RuntimeError("Phase 8.4 não detectada em leadflow_agent/search_service.py")
    if not (ROOT / "frontend/src/App.tsx").exists():
        raise RuntimeError("frontend React não encontrado")

    # Backend: status explícito para resultado parcial.
    rel = "leadflow_agent/runtime.py"
    text = read(rel)
    if 'PARTIAL_RESULTS = "partial_results"' not in text:
        text = replace_once(
            text,
            '    PARTIAL_BUDGET = "partial_budget"\n    CANCELLED = "cancelled"\n',
            '    PARTIAL_BUDGET = "partial_budget"\n    PARTIAL_RESULTS = "partial_results"\n    CANCELLED = "cancelled"\n',
            "runtime partial_results",
        )
    write(rel, text)

    rel = "leadflow_agent/agent.py"
    text = read(rel)
    if "RunStatus" not in text.split("\n", 25)[15:25]:
        text = text.replace(
            "from .runtime import BudgetExceeded, BudgetKind, RunCancelled, RunController\n",
            "from .runtime import BudgetExceeded, BudgetKind, RunCancelled, RunController, RunStatus\n",
            1,
        )
    old_quota = """        if len(leads) < goal.limit and controller.stop_reason is None:
            controller.stop_reason = (
                f"quota parcial: {len(leads)}/{goal.limit} leads elegíveis após descoberta, "
                "deduplicação e filtros"
            )
"""
    new_quota = """        if len(leads) < goal.limit and controller.stop_reason is None:
            controller.status = RunStatus.PARTIAL_RESULTS
            controller.stop_reason = (
                f"quantidade parcial: {len(leads)}/{goal.limit} leads elegíveis após descoberta, "
                "deduplicação e filtros"
            )
"""
    if "controller.status = RunStatus.PARTIAL_RESULTS" not in text:
        text = replace_once(text, old_quota, new_quota, "agent partial quota")
    write(rel, text)

    # Backend: quota fulfillment é regra da aplicação, não detalhe do frontend.
    rel = "leadflow_agent/search_service.py"
    text = read(rel)
    if "fulfill_quota: bool = True" not in text:
        text = replace_once(
            text,
            '    contact_strategy: str = "digital-first"\n    use_cache: bool = True\n',
            '    contact_strategy: str = "digital-first"\n    fulfill_quota: bool = True\n    use_cache: bool = True\n',
            "search request fulfill_quota",
        )
    if "effective_max_queries = int(request.max_queries)" not in text:
        text = replace_once(
            text,
            """    report = agent.research(
        goal,
        max_queries=request.max_queries,
""",
            """    effective_max_queries = int(request.max_queries)
    effective_pool_multiplier = int(request.filter_pool_multiplier)
    if request.fulfill_quota:
        # Busca normal é orientada à quantidade solicitada. Clientes antigos
        # ainda podem enviar 6 queries / pool 2x; o backend garante um piso
        # seguro sem ultrapassar os hard budgets já existentes.
        effective_max_queries = max(
            effective_max_queries,
            min(20, max(10, int(request.limit))),
        )
        effective_pool_multiplier = max(effective_pool_multiplier, 5)

    report = agent.research(
        goal,
        max_queries=effective_max_queries,
""",
            "search effective max_queries",
        )
        text = text.replace(
            "        filter_pool_multiplier=request.filter_pool_multiplier,\n",
            "        filter_pool_multiplier=effective_pool_multiplier,\n",
            1,
        )
    write(rel, text)

    rel = "leadflow_agent/api.py"
    text = read(rel)
    if "fulfill_quota: bool = True" not in text:
        text = replace_once(
            text,
            '    contact_strategy: Literal["digital-first", "multichannel"] = "digital-first"\n    use_cache: bool = True\n',
            '    contact_strategy: Literal["digital-first", "multichannel"] = "digital-first"\n    fulfill_quota: bool = True\n    use_cache: bool = True\n',
            "api fulfill_quota model",
        )
        text = replace_once(
            text,
            "            contact_strategy=self.contact_strategy,\n            use_cache=self.use_cache,\n",
            "            contact_strategy=self.contact_strategy,\n            fulfill_quota=self.fulfill_quota,\n            use_cache=self.use_cache,\n",
            "api fulfill_quota mapping",
        )
    text = text.replace(
        '{"completed", "partial_budget", "cancelled", "failed"}',
        '{"completed", "partial_budget", "partial_results", "cancelled", "failed"}',
    )
    write(rel, text)

    # Planner: mais ângulos disponíveis quando a quantidade ainda exige amplitude.
    rel = "leadflow_agent/planner.py"
    text = read(rel)
    start = text.find("def _expand_plan_to_budget")
    end = text.find("\ndef build_plan", start)
    if start == -1 or end == -1:
        raise RuntimeError("planner: função _expand_plan_to_budget não encontrada")
    expanded = """def _expand_plan_to_budget(plan: QueryPlan, goal: SearchGoal, *, max_queries: int) -> QueryPlan:
    \"""Expande planos curtos com ângulos determinísticos relevantes.\"""
    base = goal.segment.strip()
    folded = base.casefold()
    supplements = [
        base,
        f"{base} empresa",
        f"{base} profissional",
        f"{base} serviços",
        f"{base} orçamento",
        f"{base} Instagram",
        f"{base} WhatsApp",
        f"{base} contato",
        f"{base} negócios locais",
        f"{base} região",
        f"{base} empresa local",
        f"{base} contato comercial",
        f"{base} perfil Instagram",
        f"{base} site oficial",
        f"{base} avaliações",
        f"{base} catálogo",
        f"{base} atendimento local",
        f"{base} perto",
        f"{base} telefone celular",
        f"{base} presença digital",
    ]
    if "marcenar" in folded or "móveis planejados" in folded or "moveis planejados" in folded:
        supplements = [
            base,
            "móveis planejados",
            "marceneiro",
            "móveis sob medida",
            "fabricação de móveis sob medida",
            "marcenaria artesanal",
            "projetos de marcenaria",
            "móveis personalizados",
            "fábrica de móveis planejados",
            "planejados sob medida",
            "marcenaria planejada",
            "marcenaria residencial",
            "marcenaria comercial",
            "armários planejados",
            "cozinhas planejadas",
            "móveis planejados quarto",
            "marcenaria Instagram",
            "marcenaria contato",
            "móveis planejados Instagram",
            "móveis sob medida contato",
        ]

    combined: list[str] = []
    for query in [*plan.queries, *supplements]:
        query = " ".join(query.split())
        if query and query.casefold() not in {item.casefold() for item in combined}:
            combined.append(query)
        if len(combined) >= max(1, max_queries):
            break
    plan.queries = combined
    return plan

"""
    text = text[:start] + expanded + text[end + 1:]
    write(rel, text)

    # Frontend v0: PT-BR como idioma oficial e defaults alinhados com o backend.
    write('frontend/src/App.tsx', 'import { useEffect, useMemo, useState } from \'react\'\nimport { useMutation, useQuery } from \'@tanstack/react-query\'\nimport {\n  ArrowSyncRegular,\n  CloudCheckmarkRegular,\n  ErrorCircleRegular,\n  SearchRegular,\n} from \'@fluentui/react-icons\'\nimport { api } from \'./lib/api\'\nimport type { RunSnapshot, SearchPayload } from \'./lib/types\'\nimport { providerLabel, runStatusLabel } from \'./lib/ptBR\'\nimport { NavRail } from \'./components/NavRail\'\nimport { SearchPanel } from \'./components/SearchPanel\'\nimport { LeadTable } from \'./components/LeadTable\'\nimport { LeadInspector } from \'./components/LeadInspector\'\nimport { StatusDot } from \'./components/StatusDot\'\nimport { useWorkspaceStore } from \'./store/useWorkspaceStore\'\n\nconst terminal = new Set([\'completed\', \'partial_budget\', \'partial_results\', \'cancelled\', \'failed\'])\n\nfunction App() {\n  const [run, setRun] = useState<RunSnapshot | null>(null)\n  const [lastError, setLastError] = useState<string | null>(null)\n  const { result, selectedLead, setResult, setSelectedLead, reset } = useWorkspaceStore()\n\n  const health = useQuery({ queryKey: [\'health\'], queryFn: api.health, refetchInterval: 15000 })\n  const segments = useQuery({ queryKey: [\'segments\'], queryFn: api.segments, enabled: health.isSuccess })\n  const profiles = useQuery({ queryKey: [\'profiles\'], queryFn: api.profiles, enabled: health.isSuccess })\n  const providers = useQuery({ queryKey: [\'providers\'], queryFn: api.providers, enabled: health.isSuccess })\n\n  const start = useMutation({\n    mutationFn: api.startRun,\n    onSuccess: (snapshot) => {\n      setLastError(null)\n      reset()\n      setRun(snapshot)\n    },\n    onError: (error) => setLastError(error instanceof Error ? error.message : \'Não foi possível iniciar a busca.\'),\n  })\n\n  const statusQuery = useQuery({\n    queryKey: [\'run\', run?.id],\n    queryFn: () => api.getRun(run!.id),\n    enabled: Boolean(run?.id && !terminal.has(run.status)),\n    refetchInterval: 650,\n  })\n\n  useEffect(() => {\n    if (statusQuery.data) setRun(statusQuery.data)\n  }, [statusQuery.data])\n\n  const resultQuery = useQuery({\n    queryKey: [\'run-result\', run?.id],\n    queryFn: () => api.getResult(run!.id),\n    enabled: Boolean(run?.id && terminal.has(run.status) && run.status !== \'failed\'),\n    retry: 2,\n  })\n\n  useEffect(() => {\n    if (resultQuery.data) setResult(resultQuery.data)\n  }, [resultQuery.data, setResult])\n\n  useEffect(() => {\n    if (run?.status === \'failed\') {\n      setLastError(run.error?.message || \'A pesquisa falhou.\')\n    }\n  }, [run])\n\n  const cancel = useMutation({\n    mutationFn: () => api.cancelRun(run!.id),\n    onSuccess: setRun,\n    onError: (error) => setLastError(error instanceof Error ? error.message : \'Não foi possível cancelar.\'),\n  })\n\n  const isRunning = Boolean(run && !terminal.has(run.status))\n  const apiOnline = health.isSuccess\n  const returned = result?.run?.returned_results ?? result?.leads?.length ?? 0\n  const requested = result?.run?.requested_results ?? 0\n  const usage = result?.run?.usage\n  const quotaPartial = Boolean(result && result.run.quota_fulfilled === false && requested > returned)\n\n  const providerSummary = useMemo(() => {\n    const configured = health.data?.configured\n    if (!configured) return \'—\'\n    const names = Object.entries(configured)\n      .filter(([, value]) => value)\n      .map(([name]) => providerLabel(name))\n    return names.length ? names.join(\' · \') : \'nenhum provedor\'\n  }, [health.data])\n\n  function startSearch(payload: SearchPayload) {\n    setRun(null)\n    setResult(null)\n    start.mutate(payload)\n  }\n\n  return (\n    <div className="app-stage">\n      <div className="ambient ambient--one" aria-hidden="true" />\n      <div className="ambient ambient--two" aria-hidden="true" />\n      <div className="app-shell">\n        <NavRail />\n        <main className="workspace">\n          <header className="topbar">\n            <div className="topbar__context">\n              <span className="workspace-label">LeadFlow</span>\n              <span className="topbar-divider" />\n              <span>Descobrir</span>\n            </div>\n            <div className="topbar__status">\n              {apiOnline ? <StatusDot tone="online" label="API local" /> : <StatusDot tone="offline" label="API indisponível" />}\n              <span className="configured-providers">{providerSummary}</span>\n            </div>\n          </header>\n\n          <div className="workspace-body">\n            <section className="primary-pane">\n              <SearchPanel\n                segments={segments.data}\n                profiles={profiles.data}\n                providers={providers.data}\n                health={health.data}\n                running={isRunning || start.isPending}\n                onSearch={startSearch}\n                onCancel={() => run && cancel.mutate()}\n              />\n\n              {isRunning && (\n                <div className="run-banner" role="status" aria-live="polite">\n                  <div className="run-banner__signal"><span /><span /><span /></div>\n                  <div><strong>Pesquisa em andamento</strong><span>{run?.status === \'cancelling\' ? \'Finalizando com segurança…\' : \'LeadFlow está descobrindo e qualificando oportunidades.\'}</span></div>\n                  <div className="run-banner__id">{run?.id.slice(0, 8)}</div>\n                </div>\n              )}\n\n              {lastError && (\n                <div className="message-bar message-bar--error" role="alert">\n                  <ErrorCircleRegular />\n                  <div><strong>Não foi possível concluir a operação.</strong><span>{lastError}</span></div>\n                  <button className="icon-button" onClick={() => setLastError(null)} aria-label="Dispensar erro">×</button>\n                </div>\n              )}\n\n              {quotaPartial && (\n                <div className="message-bar message-bar--warning" role="status">\n                  <ErrorCircleRegular />\n                  <div>\n                    <strong>Quantidade parcial de leads.</strong>\n                    <span>\n                      Encontramos {returned} de {requested}. O LeadFlow tentou ampliar a descoberta sem reduzir os critérios de qualidade\n                      {usage?.search_calls ? ` e utilizou ${usage.search_calls} buscas.` : \'.\'}\n                    </span>\n                  </div>\n                </div>\n              )}\n\n              <section className="results-surface">\n                <div className="results-toolbar">\n                  <div>\n                    <p className="eyebrow">Fluxo de oportunidades</p>\n                    <h2>{result ? `${returned} leads encontrados` : \'Resultados\'}</h2>\n                  </div>\n                  {result && (\n                    <div className="results-summary">\n                      <span>{returned}/{requested || returned}</span>\n                      <span>{providerLabel(run?.provider)}</span>\n                      <span className={`run-state run-state--${result.run.status}`}>{runStatusLabel(result.run.status)}</span>\n                    </div>\n                  )}\n                </div>\n\n                {!apiOnline && health.isError ? (\n                  <div className="empty-state">\n                    <CloudCheckmarkRegular />\n                    <h3>Inicie a API local</h3>\n                    <p>Abra outro terminal na raiz do projeto e execute <code>leadflow api</code>.</p>\n                    <button className="button button--quiet" onClick={() => health.refetch()}><ArrowSyncRegular /> Tentar novamente</button>\n                  </div>\n                ) : !result ? (\n                  <div className="empty-state empty-state--quiet">\n                    <div className="empty-signal"><SearchRegular /></div>\n                    <h3>Seu próximo lead ainda não está aqui.</h3>\n                    <p>Defina segmento e localização. Os resultados qualificados aparecem nesta área sem tirar você do contexto.</p>\n                  </div>\n                ) : result.leads.length === 0 ? (\n                  <div className="empty-state"><SearchRegular /><h3>Nenhum lead elegível</h3><p>A pesquisa terminou sem resultados que passassem pelos critérios atuais. Ajuste os filtros ou amplie a busca.</p></div>\n                ) : (\n                  <LeadTable leads={result.leads} selected={selectedLead} onSelect={setSelectedLead} />\n                )}\n              </section>\n            </section>\n\n            {selectedLead && <LeadInspector lead={selectedLead} onClose={() => setSelectedLead(null)} />}\n          </div>\n\n          <footer className="statusbar">\n            <div><StatusDot tone={apiOnline ? \'online\' : \'offline\'} label={apiOnline ? \'Núcleo conectado\' : \'Núcleo desconectado\'} /><span>Contrato {health.data?.frontend_contract_version ?? \'—\'}</span></div>\n            <div>\n              {usage && <span>Buscas {usage.search_calls ?? 0} · IA {usage.llm_calls ?? 0} · HTTP {usage.website_audits ?? 0} · Navegador {usage.browser_audits ?? 0} · Visual {usage.visual_audits ?? 0}</span>}\n              <span>LeadFlow alpha</span>\n            </div>\n          </footer>\n        </main>\n      </div>\n    </div>\n  )\n}\n\nexport default App\n')
    write('frontend/src/components/SearchPanel.tsx', 'import { useMemo, useState } from \'react\'\nimport {\n  ChevronDownRegular,\n  SearchRegular,\n  StopRegular,\n} from \'@fluentui/react-icons\'\nimport type {\n  Health,\n  ProfileCatalog,\n  ProviderCatalog,\n  SearchPayload,\n  SegmentCatalog,\n} from \'../lib/types\'\nimport { profileLabel, providerLabel } from \'../lib/ptBR\'\n\nexport type SearchFormValue = SearchPayload\n\nconst defaultValue: SearchFormValue = {\n  segment: \'marcenaria\',\n  city: \'Praia Grande\',\n  state: \'SP\',\n  country: \'Brazil\',\n  limit: 10,\n  max_queries: 10,\n  profile: \'website-sales\',\n  provider: \'auto\',\n  no_ai: false,\n  require_phone: false,\n  filter_pool_multiplier: 5,\n  contact_strategy: \'digital-first\',\n  fulfill_quota: true,\n  use_cache: true,\n  refresh_cache: false,\n  cache_ttl_days: 14,\n  use_memory: true,\n  filters: {\n    website: \'any\',\n    instagram: \'any\',\n    phone: \'any\',\n    email: \'any\',\n    readiness: \'any\',\n    require_any_contact: false,\n  },\n  features: {\n    investigate: true,\n    investigation_limit: 3,\n    investigation_budget: 2,\n    audit_websites: true,\n    audit_limit: 3,\n    audit_timeout: 8,\n    browser_audit: false,\n    browser_audit_limit: 3,\n    browser_timeout: 12,\n    visual_audit: false,\n    visual_audit_limit: 3,\n  },\n  budgets: {\n    max_search_calls: 20,\n    max_llm_calls: 30,\n    max_website_audits: 25,\n    max_browser_audits: 10,\n    max_visual_audits: 10,\n  },\n}\n\ntype Props = {\n  segments?: SegmentCatalog\n  profiles?: ProfileCatalog\n  providers?: ProviderCatalog\n  health?: Health\n  running: boolean\n  onSearch: (payload: SearchPayload) => void\n  onCancel: () => void\n}\n\nexport function SearchPanel({ segments, profiles, providers, health, running, onSearch, onCancel }: Props) {\n  const [value, setValue] = useState<SearchFormValue>(defaultValue)\n  const [advanced, setAdvanced] = useState(false)\n\n  const allSegments = useMemo(\n    () => segments?.groups.flatMap((group) => group.items) ?? [],\n    [segments],\n  )\n\n  function submit(event: React.FormEvent) {\n    event.preventDefault()\n    if (!value.segment.trim() || !value.city.trim() || running) return\n    onSearch({ ...value, segment: value.segment.trim(), city: value.city.trim(), state: value.state.trim() })\n  }\n\n  const providerOptions = [\n    { slug: \'auto\', label: \'Automático\' },\n    ...(providers?.items ?? []).filter((item) => item.slug !== \'gemini\'),\n  ]\n\n  return (\n    <form className="search-panel" onSubmit={submit}>\n      <div className="search-panel__heading">\n        <div>\n          <p className="eyebrow">Área de descoberta</p>\n          <h1>Encontre a próxima oportunidade.</h1>\n        </div>\n        <div className="research-mode" aria-label="Modo de pesquisa">\n          <span>Núcleo de inteligência</span>\n          <strong>{health?.configured.gemini ? \'Gemini ativo\' : \'Modo básico\'}</strong>\n        </div>\n      </div>\n\n      <div className="search-grid">\n        <label className="field field--wide">\n          <span>Segmento</span>\n          <input\n            list="segments"\n            value={value.segment}\n            onChange={(event) => setValue({ ...value, segment: event.target.value })}\n            placeholder="Ex.: marcenaria, vidraçaria, clínica..."\n          />\n          <datalist id="segments">\n            {allSegments.map((item) => (\n              <option key={item.slug} value={item.label} />\n            ))}\n          </datalist>\n        </label>\n\n        <label className="field field--wide">\n          <span>Cidade</span>\n          <input value={value.city} onChange={(event) => setValue({ ...value, city: event.target.value })} />\n        </label>\n\n        <label className="field field--state">\n          <span>UF</span>\n          <input\n            value={value.state}\n            maxLength={3}\n            onChange={(event) => setValue({ ...value, state: event.target.value.toUpperCase() })}\n          />\n        </label>\n\n        <label className="field field--count">\n          <span>Leads</span>\n          <input\n            type="number"\n            min={1}\n            max={100}\n            value={value.limit}\n            onChange={(event) => setValue({ ...value, limit: Number(event.target.value) || 1 })}\n          />\n        </label>\n\n        <label className="field">\n          <span>Perfil</span>\n          <select value={value.profile} onChange={(event) => setValue({ ...value, profile: event.target.value })}>\n            {(profiles?.items ?? []).map((item) => (\n              <option key={item.slug} value={item.slug}>{profileLabel(item.slug, item.label)}</option>\n            ))}\n          </select>\n        </label>\n\n        <label className="field">\n          <span>Provedor</span>\n          <select\n            value={value.provider}\n            onChange={(event) => setValue({ ...value, provider: event.target.value as SearchPayload[\'provider\'] })}\n          >\n            {providerOptions.map((item) => {\n              const configured = item.slug === \'auto\' || (\'configured\' in item && item.configured)\n              return (\n                <option key={item.slug} value={item.slug} disabled={!configured}>\n                  {providerLabel(item.slug)}{configured ? \'\' : \' · não configurado\'}\n                </option>\n              )\n            })}\n          </select>\n        </label>\n      </div>\n\n      <div className="quick-options">\n        <label className="check-control">\n          <input\n            type="checkbox"\n            checked={value.features.investigate}\n            onChange={(event) => setValue({ ...value, features: { ...value.features, investigate: event.target.checked } })}\n          />\n          <span>Investigar</span>\n        </label>\n        <label className="check-control">\n          <input\n            type="checkbox"\n            checked={value.features.audit_websites}\n            onChange={(event) => setValue({ ...value, features: { ...value.features, audit_websites: event.target.checked } })}\n          />\n          <span>Auditar sites</span>\n        </label>\n        <label className="check-control">\n          <input\n            type="checkbox"\n            checked={value.features.browser_audit}\n            onChange={(event) => setValue({ ...value, features: { ...value.features, browser_audit: event.target.checked } })}\n          />\n          <span>Navegador / UX</span>\n        </label>\n        <label className="check-control">\n          <input\n            type="checkbox"\n            checked={value.features.visual_audit}\n            disabled={!health?.configured.gemini}\n            onChange={(event) => setValue({ ...value, features: { ...value.features, visual_audit: event.target.checked } })}\n          />\n          <span>Visual por IA</span>\n        </label>\n      </div>\n\n      <div className={`advanced-panel ${advanced ? \'is-open\' : \'\'}`}>\n        <button className="advanced-toggle" type="button" onClick={() => setAdvanced((current) => !current)}>\n          <ChevronDownRegular aria-hidden="true" />\n          Filtros avançados\n        </button>\n        {advanced && (\n          <div className="advanced-grid">\n            <label className="field"><span>Site</span><select value={value.filters.website} onChange={(e) => setValue({ ...value, filters: { ...value.filters, website: e.target.value as NonNullable<SearchPayload[\'filters\'][\'website\']> } })}><option value="any">Qualquer</option><option value="not_found">Sem site verificado</option><option value="present">Com site</option><option value="unknown">Desconhecido</option><option value="unreachable">Inacessível</option></select></label>\n            <label className="field"><span>Instagram</span><select value={value.filters.instagram} onChange={(e) => setValue({ ...value, filters: { ...value.filters, instagram: e.target.value as NonNullable<SearchPayload[\'filters\'][\'instagram\']> } })}><option value="any">Qualquer</option><option value="present">Presente</option><option value="missing">Ausente</option></select></label>\n            <label className="field"><span>Celular</span><select value={value.filters.phone} onChange={(e) => setValue({ ...value, filters: { ...value.filters, phone: e.target.value as NonNullable<SearchPayload[\'filters\'][\'phone\']> } })}><option value="any">Qualquer</option><option value="present">Presente</option><option value="missing">Ausente</option></select></label>\n            <label className="field"><span>Prontidão</span><select value={value.filters.readiness} onChange={(e) => setValue({ ...value, filters: { ...value.filters, readiness: e.target.value as NonNullable<SearchPayload[\'filters\'][\'readiness\']> } })}><option value="any">PRONTO + VERIFICAR</option><option value="ready">PRONTO</option><option value="verify">VERIFICAR</option></select></label>\n            <label className="field"><span>Potencial mínimo</span><input type="number" min={0} max={100} value={value.filters.min_opportunity_score ?? \'\'} placeholder="0–100" onChange={(e) => setValue({ ...value, filters: { ...value.filters, min_opportunity_score: e.target.value ? Number(e.target.value) : undefined } })} /></label>\n            <label className="field"><span>Amplitude da busca</span><select value={value.filter_pool_multiplier} onChange={(e) => setValue({ ...value, filter_pool_multiplier: Number(e.target.value) })}><option value={1}>1×</option><option value={2}>2×</option><option value={3}>3×</option><option value={4}>4×</option><option value={5}>5×</option><option value={6}>6×</option><option value={7}>7×</option><option value={8}>8×</option></select></label>\n          </div>\n        )}\n      </div>\n\n      <div className="search-actions">\n        <p className="search-hint">A busca roda em segundo plano e tenta completar a quantidade solicitada sem reduzir os critérios de qualidade.</p>\n        {running ? (\n          <button className="button button--quiet" type="button" onClick={onCancel}>\n            <StopRegular aria-hidden="true" /> Cancelar\n          </button>\n        ) : (\n          <button className="button button--primary" type="submit">\n            <SearchRegular aria-hidden="true" /> Buscar leads\n          </button>\n        )}\n      </div>\n    </form>\n  )\n}\n')
    write('frontend/src/components/LeadInspector.tsx', 'import { useEffect, useMemo, useState } from \'react\'\nimport {\n  ArrowUpRightRegular,\n  CheckmarkCircleRegular,\n  ClipboardRegular,\n  DismissRegular,\n  GlobeRegular,\n  MailRegular,\n  PhoneRegular,\n  SendRegular,\n  ShieldCheckmarkRegular,\n} from \'@fluentui/react-icons\'\nimport { api } from \'../lib/api\'\nimport type { ContactPreparation, LeadCard } from \'../lib/types\'\nimport {\n  identityLabel,\n  opportunityLabel,\n  readinessLabel,\n  serviceFitLabel,\n} from \'../lib/ptBR\'\n\nfunction percent(value?: number) {\n  if (value == null) return \'—\'\n  return `${Math.round(value <= 1 ? value * 100 : value)}%`\n}\n\nfunction score(value?: number | null) {\n  return value == null ? \'—\' : `${Math.round(value)}`\n}\n\ntype Props = {\n  lead: LeadCard | null\n  onClose: () => void\n}\n\nexport function LeadInspector({ lead, onClose }: Props) {\n  const [contact, setContact] = useState<ContactPreparation | null>(null)\n  const [message, setMessage] = useState(\'\')\n  const [loadingContact, setLoadingContact] = useState(false)\n  const [copied, setCopied] = useState(false)\n\n  useEffect(() => {\n    setContact(null)\n    setMessage(\'\')\n    setCopied(false)\n  }, [lead])\n\n  const socials = useMemo(() => lead?.contact?.socials ?? [], [lead])\n  if (!lead) return null\n  const activeLead = lead\n\n  async function prepare() {\n    setLoadingContact(true)\n    try {\n      const prepared = await api.prepareContact(activeLead)\n      setContact(prepared)\n      setMessage(prepared.message)\n    } finally {\n      setLoadingContact(false)\n    }\n  }\n\n  async function copyMessage() {\n    await navigator.clipboard.writeText(message)\n    setCopied(true)\n    window.setTimeout(() => setCopied(false), 1600)\n  }\n\n  async function openPrimary() {\n    if (!contact || contact.channel === \'none\') return\n    if (contact.channel === \'instagram\' && contact.instagram_url) {\n      void navigator.clipboard.writeText(message)\n      window.open(contact.instagram_url, \'_blank\', \'noopener,noreferrer\')\n      return\n    }\n    if (contact.whatsapp_number) {\n      const url = `https://wa.me/${contact.whatsapp_number}?text=${encodeURIComponent(message)}`\n      window.open(url, \'_blank\', \'noopener,noreferrer\')\n    }\n  }\n\n  return (\n    <aside className="inspector" aria-label={`Detalhes de ${lead.name}`}>\n      <div className="inspector__top">\n        <div>\n          <p className="eyebrow">Lead selecionado</p>\n          <h2>{lead.name}</h2>\n          <div className="lead-meta-line">\n            <span>{opportunityLabel(lead.opportunity?.type)}</span>\n            <span>·</span>\n            <span>{readinessLabel(lead.opportunity?.actionable)}</span>\n          </div>\n        </div>\n        <button className="icon-button" type="button" aria-label="Fechar detalhes" onClick={onClose}>\n          <DismissRegular />\n        </button>\n      </div>\n\n      <div className="fit-hero">\n        <div className="fit-orb" style={{ \'--fit\': `${Math.min(100, Math.max(0, lead.opportunity?.score ?? 0)) * 3.6}deg` } as React.CSSProperties}>\n          <div><strong>{lead.opportunity?.score ?? 0}</strong><span>pot.</span></div>\n        </div>\n        <div>\n          <span className="section-kicker">Potencial da oportunidade</span>\n          <strong className="fit-summary">{serviceFitLabel(lead.opportunity?.service_fit)}</strong>\n          <p>{lead.opportunity?.reasons?.[0] || \'Revise os sinais antes de abordar.\'}</p>\n        </div>\n      </div>\n\n      <section className="inspector-section">\n        <div className="section-title"><span>Contato</span><span className="section-index">01</span></div>\n        <div className="contact-lines">\n          <div><PhoneRegular /><span>{lead.contact?.phone || \'Sem celular\'}</span></div>\n          <div><MailRegular /><span>{lead.contact?.email || \'Sem e-mail\'}</span></div>\n          <div><GlobeRegular /><span>{lead.website?.url || \'Sem site identificado\'}</span></div>\n        </div>\n        {!contact ? (\n          <button className="button button--primary button--full" type="button" onClick={prepare} disabled={loadingContact}>\n            <SendRegular /> {loadingContact ? \'Preparando…\' : \'Preparar contato\'}\n          </button>\n        ) : (\n          <div className="contact-composer">\n            <div className="contact-route">\n              <span>Canal recomendado</span>\n              <strong>{contact.label}</strong>\n            </div>\n            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={7} aria-label="Mensagem de contato" />\n            <div className="composer-actions">\n              <button className="button button--primary" type="button" disabled={contact.channel === \'none\'} onClick={openPrimary}>\n                <ArrowUpRightRegular /> {contact.channel === \'instagram\' ? \'Abrir Instagram\' : \'Abrir WhatsApp\'}\n              </button>\n              <button className="button button--quiet" type="button" onClick={copyMessage}>\n                {copied ? <CheckmarkCircleRegular /> : <ClipboardRegular />}{copied ? \'Copiado\' : \'Copiar\'}\n              </button>\n            </div>\n          </div>\n        )}\n      </section>\n\n      <section className="inspector-section">\n        <div className="section-title"><span>Sinais</span><span className="section-index">02</span></div>\n        <div className="signal-grid">\n          <div className="signal"><span>Identidade</span><strong>{percent(lead.identity?.confidence)}</strong><small>{identityLabel(lead.identity?.status)}</small></div>\n          <div className="signal"><span>Técnico</span><strong>{score(lead.website?.technical_score)}</strong><small>Saúde do site</small></div>\n          <div className="signal"><span>UX no navegador</span><strong>{score(lead.website?.browser_ux_score)}</strong><small>Experiência objetiva</small></div>\n          <div className="signal"><span>Visual</span><strong>{score(lead.website?.visual_score)}</strong><small>Qualidade visual</small></div>\n        </div>\n      </section>\n\n      <section className="inspector-section">\n        <div className="section-title"><span>Evidências e cuidados</span><span className="section-index">03</span></div>\n        <ul className="reason-list">\n          {(lead.opportunity?.reasons ?? []).slice(0, 5).map((reason) => <li key={reason}><CheckmarkCircleRegular />{reason}</li>)}\n          {(lead.opportunity?.cautions ?? []).slice(0, 4).map((reason) => <li className="caution" key={reason}><ShieldCheckmarkRegular />{reason}</li>)}\n          {!lead.opportunity?.reasons?.length && !lead.opportunity?.cautions?.length ? <li className="muted">Sem sinais adicionais no contrato atual.</li> : null}\n        </ul>\n      </section>\n\n      {socials.length > 0 && (\n        <section className="inspector-section inspector-section--last">\n          <div className="section-title"><span>Fontes</span><span className="section-index">04</span></div>\n          <div className="source-stack">\n            {socials.slice(0, 5).map((url) => (\n              <a key={url} href={url} target="_blank" rel="noreferrer">{url.replace(/^https?:\\/\\//, \'\').replace(/\\/$/, \'\')}<ArrowUpRightRegular /></a>\n            ))}\n          </div>\n        </section>\n      )}\n    </aside>\n  )\n}\n')
    write('frontend/src/components/LeadTable.tsx', 'import { useState } from \'react\'\nimport {\n  ArrowSortDownRegular,\n  ArrowSortUpRegular,\n  OpenRegular,\n} from \'@fluentui/react-icons\'\nimport {\n  createColumnHelper,\n  createSortedRowModel,\n  rowSortingFeature,\n  sortFns,\n  tableFeatures,\n  useTable,\n  type SortingState,\n} from \'@tanstack/react-table\'\nimport type { LeadCard } from \'../lib/types\'\nimport { opportunityLabel, readinessLabel } from \'../lib/ptBR\'\n\nconst features = tableFeatures({\n  rowSortingFeature,\n  sortedRowModel: createSortedRowModel(),\n  sortFns,\n})\n\nconst column = createColumnHelper<typeof features, LeadCard>()\n\nconst columns = column.columns([\n  column.accessor((lead) => lead.opportunity?.score ?? 0, {\n    id: \'fit\',\n    header: \'Potencial\',\n    cell: (info) => <span className="fit-value">{info.getValue()}</span>,\n  }),\n  column.accessor(\'name\', {\n    header: \'Empresa\',\n    cell: (info) => (\n      <div className="company-cell">\n        <strong>{info.getValue()}</strong>\n        <span>{[info.row.original.location?.city, info.row.original.location?.state].filter(Boolean).join(\' · \')}</span>\n      </div>\n    ),\n  }),\n  column.accessor((lead) => lead.opportunity?.type ?? \'review_needed\', {\n    id: \'opportunity\',\n    header: \'Oportunidade\',\n    cell: (info) => <span>{opportunityLabel(info.getValue()).toUpperCase()}</span>,\n  }),\n  column.accessor((lead) => readinessLabel(lead.opportunity?.actionable), {\n    id: \'readiness\',\n    header: \'Estado\',\n    cell: (info) => {\n      const ready = info.getValue() === \'PRONTO\'\n      return <span className={`state-label state-label--${ready ? \'ready\' : \'verify\'}`}>{info.getValue()}</span>\n    },\n  }),\n  column.accessor((lead) => lead.contact?.phone ?? \'\', {\n    id: \'phone\',\n    header: \'Celular\',\n    cell: (info) => info.getValue() || <span className="muted">—</span>,\n  }),\n  column.accessor((lead) => lead.website?.status ?? \'unknown\', {\n    id: \'website\',\n    header: \'Site\',\n    cell: (info) => {\n      const lead = info.row.original\n      return lead.website?.url ? (\n        <span className="website-cell">{lead.website.url.replace(/^https?:\\/\\//, \'\').replace(/\\/$/, \'\')}</span>\n      ) : (\n        <span className="muted">{info.getValue() === \'not_found\' ? \'Não encontrado\' : \'—\'}</span>\n      )\n    },\n  }),\n  column.display({\n    id: \'open\',\n    header: \'\',\n    enableSorting: false,\n    cell: () => <OpenRegular aria-hidden="true" className="row-open-icon" />,\n  }),\n])\n\ntype Props = {\n  leads: LeadCard[]\n  selected: LeadCard | null\n  onSelect: (lead: LeadCard) => void\n}\n\nexport function LeadTable({ leads, selected, onSelect }: Props) {\n  const [sorting, setSorting] = useState<SortingState>([{ id: \'fit\', desc: true }])\n\n  const table = useTable({\n    key: \'lead-opportunity-table\',\n    features,\n    data: leads,\n    columns,\n    state: { sorting },\n    onSortingChange: setSorting,\n  })\n\n  return (\n    <div className="lead-table-wrap">\n      <table className="lead-table">\n        <thead>\n          {table.getHeaderGroups().map((group) => (\n            <tr key={group.id}>\n              {group.headers.map((header) => (\n                <th key={header.id}>\n                  {header.isPlaceholder ? null : header.column.getCanSort() ? (\n                    <button className="sort-button" onClick={header.column.getToggleSortingHandler()}>\n                      <table.FlexRender header={header} />\n                      {header.column.getIsSorted() === \'asc\' ? <ArrowSortUpRegular /> : header.column.getIsSorted() === \'desc\' ? <ArrowSortDownRegular /> : null}\n                    </button>\n                  ) : (\n                    <table.FlexRender header={header} />\n                  )}\n                </th>\n              ))}\n            </tr>\n          ))}\n        </thead>\n        <tbody>\n          {table.getRowModel().rows.map((row) => {\n            const active = selected === row.original\n            return (\n              <tr\n                key={row.id}\n                className={active ? \'is-selected\' : \'\'}\n                tabIndex={0}\n                aria-selected={active}\n                onClick={() => onSelect(row.original)}\n                onKeyDown={(event) => {\n                  if (event.key === \'Enter\' || event.key === \' \') {\n                    event.preventDefault()\n                    onSelect(row.original)\n                  }\n                }}\n              >\n                {row.getAllCells().map((cell) => (\n                  <td key={cell.id}><table.FlexRender cell={cell} /></td>\n                ))}\n              </tr>\n            )\n          })}\n        </tbody>\n      </table>\n    </div>\n  )\n}\n')
    write('frontend/src/components/NavRail.tsx', 'import {\n  CompassNorthwestRegular,\n  DataTrendingRegular,\n  HistoryRegular,\n  PeopleTeamRegular,\n  SettingsRegular,\n  SparkleRegular,\n} from \'@fluentui/react-icons\'\n\nexport function NavRail() {\n  return (\n    <nav className="nav-rail" aria-label="Navegação principal">\n      <div className="brand-mark" aria-label="LeadFlow"><span>LF</span></div>\n      <div className="nav-rail__group">\n        <button className="nav-item is-active" aria-current="page" title="Descobrir"><CompassNorthwestRegular /><span>Descobrir</span></button>\n        <button className="nav-item" disabled title="Leads — próxima etapa"><PeopleTeamRegular /><span>Leads</span></button>\n        <button className="nav-item" disabled title="Funil — próxima etapa"><DataTrendingRegular /><span>Funil</span></button>\n        <button className="nav-item" disabled title="Histórico — próxima etapa"><HistoryRegular /><span>Histórico</span></button>\n      </div>\n      <div className="nav-rail__spacer" />\n      <div className="nav-rail__group">\n        <button className="nav-item" disabled title="Análises — futura etapa"><SparkleRegular /><span>Análises</span></button>\n        <button className="nav-item" disabled title="Configurações — futura etapa"><SettingsRegular /><span>Configurações</span></button>\n      </div>\n    </nav>\n  )\n}\n')
    write('frontend/src/lib/types.ts', "export type RunStatus =\n  | 'queued'\n  | 'running'\n  | 'cancelling'\n  | 'completed'\n  | 'partial_budget'\n  | 'partial_results'\n  | 'cancelled'\n  | 'failed'\n\nexport type Health = {\n  status: string\n  api_version: string\n  frontend_contract_version: string\n  configured: {\n    gemini: boolean\n    tavily: boolean\n    brave: boolean\n    outscraper: boolean\n  }\n}\n\nexport type SegmentCatalog = {\n  groups: Array<{\n    category: string\n    items: Array<{ slug: string; label: string; aliases: string[] }>\n  }>\n  free_text_allowed: boolean\n}\n\nexport type ProfileCatalog = {\n  items: Array<{ slug: string; label: string; description: string }>\n}\n\nexport type ProviderCatalog = {\n  items: Array<{\n    slug: string\n    label: string\n    roles: string[]\n    capabilities: string[]\n    byok: boolean\n    configured: boolean\n  }>\n}\n\nexport type LeadCard = {\n  name: string\n  location: { city?: string; state?: string; country?: string }\n  contact: { phone?: string | null; email?: string | null; socials?: string[] }\n  website: {\n    url?: string | null\n    status?: string\n    technical_score?: number | null\n    browser_ux_score?: number | null\n    visual_score?: number | null\n  }\n  identity: { status?: string; confidence?: number }\n  opportunity: {\n    score?: number\n    type?: string\n    actionable?: boolean\n    service_fit?: string\n    reasons?: string[]\n    cautions?: string[]\n  }\n}\n\nexport type ResearchContract = {\n  contract_version: string\n  run: {\n    status: string\n    stop_reason?: string | null\n    started_at?: string\n    finished_at?: string\n    requested_results?: number\n    returned_results?: number\n    quota_fulfilled?: boolean\n    shortfall?: number\n    usage?: {\n      search_calls?: number\n      llm_calls?: number\n      website_audits?: number\n      browser_audits?: number\n      visual_audits?: number\n    }\n  }\n  goal: { segment?: string; city?: string; state?: string; country?: string }\n  leads: LeadCard[]\n}\n\nexport type RunSnapshot = {\n  id: string\n  status: RunStatus\n  created_at: string\n  started_at?: string | null\n  finished_at?: string | null\n  provider?: string | null\n  db_run_id?: number | null\n  error?: { code: string; message: string; retryable?: boolean } | null\n}\n\nexport type SearchPayload = {\n  segment: string\n  city: string\n  state: string\n  country: string\n  limit: number\n  max_queries: number\n  profile: string\n  provider: 'auto' | 'tavily' | 'brave' | 'outscraper'\n  no_ai: boolean\n  require_phone: boolean\n  filter_pool_multiplier: number\n  contact_strategy: 'digital-first' | 'multichannel'\n  fulfill_quota: boolean\n  use_cache: boolean\n  refresh_cache: boolean\n  cache_ttl_days: number\n  use_memory: boolean\n  filters: {\n    website?: 'any' | 'unknown' | 'present' | 'not_found' | 'unreachable'\n    instagram?: 'any' | 'present' | 'missing'\n    phone?: 'any' | 'present' | 'missing'\n    email?: 'any' | 'present' | 'missing'\n    readiness?: 'any' | 'ready' | 'verify'\n    min_opportunity_score?: number\n    require_any_contact: boolean\n  }\n  features: {\n    investigate: boolean\n    investigation_limit: number\n    investigation_budget: number\n    audit_websites: boolean\n    audit_limit: number\n    audit_timeout: number\n    browser_audit: boolean\n    browser_audit_limit: number\n    browser_timeout: number\n    visual_audit: boolean\n    visual_audit_limit: number\n  }\n  budgets: {\n    max_search_calls: number\n    max_llm_calls: number\n    max_website_audits: number\n    max_browser_audits: number\n    max_visual_audits: number\n  }\n}\n\nexport type ContactPreparation = {\n  channel: 'whatsapp' | 'whatsapp_test' | 'instagram' | 'none'\n  label: string\n  message: string\n  whatsapp_number?: string | null\n  whatsapp_url?: string | null\n  instagram_url?: string | null\n  whatsapp_source?: string | null\n}\n")
    write('frontend/src/lib/ptBR.ts', "const OPPORTUNITY_LABELS: Record<string, string> = {\n  new_site: 'Novo site',\n  rebuild: 'Reconstrução',\n  redesign: 'Redesign',\n  optimization: 'Otimização',\n  review_needed: 'Revisar',\n  low_opportunity: 'Baixa oportunidade',\n  unknown: 'Não definida',\n}\n\nconst SERVICE_FIT_LABELS: Record<string, string> = {\n  new_website: 'Novo site',\n  website_rebuild: 'Reconstrução do site',\n  website_redesign: 'Redesign do site',\n  website_optimization: 'Otimização do site',\n  website_review: 'Revisão do site',\n  visual_review: 'Revisão visual',\n  investigate_first: 'Investigar primeiro',\n  do_not_contact: 'Não contatar',\n  unknown: 'Revisar oportunidade',\n}\n\nconst IDENTITY_LABELS: Record<string, string> = {\n  matched: 'Correspondência confirmada',\n  probable_match: 'Correspondência provável',\n  unverified: 'Não verificada',\n  ambiguous: 'Ambígua',\n  mismatch: 'Incompatível',\n  unknown: 'Não verificada',\n}\n\nconst RUN_STATUS_LABELS: Record<string, string> = {\n  queued: 'Na fila',\n  running: 'Pesquisando',\n  cancelling: 'Cancelando',\n  completed: 'Concluída',\n  partial_budget: 'Parcial · limite atingido',\n  partial_results: 'Parcial',\n  cancelled: 'Cancelada',\n  failed: 'Falhou',\n}\n\nconst PROFILE_LABELS: Record<string, string> = {\n  balanced: 'Equilibrado',\n  'website-sales': 'Venda de sites',\n  'new-site': 'Novo site',\n  redesign: 'Redesign',\n  'visual-redesign': 'Redesign visual',\n  'ready-only': 'Somente prontos',\n  'instagram-first': 'Instagram primeiro',\n  'phone-first': 'Celular primeiro',\n}\n\nexport function opportunityLabel(value?: string) {\n  return OPPORTUNITY_LABELS[value || 'unknown'] || value || 'Não definida'\n}\n\nexport function serviceFitLabel(value?: string) {\n  return SERVICE_FIT_LABELS[value || 'unknown'] || value?.replaceAll('_', ' ') || 'Revisar oportunidade'\n}\n\nexport function identityLabel(value?: string) {\n  return IDENTITY_LABELS[value || 'unknown'] || value?.replaceAll('_', ' ') || 'Não verificada'\n}\n\nexport function readinessLabel(actionable?: boolean) {\n  return actionable ? 'PRONTO' : 'VERIFICAR'\n}\n\nexport function runStatusLabel(value?: string) {\n  return RUN_STATUS_LABELS[value || ''] || value?.replaceAll('_', ' ') || '—'\n}\n\nexport function profileLabel(slug: string, fallback?: string) {\n  return PROFILE_LABELS[slug] || fallback || slug\n}\n\nexport function providerLabel(value?: string | null) {\n  if (!value) return 'Provedor'\n  const labels: Record<string, string> = {\n    auto: 'Automático',\n    tavily: 'Tavily',\n    brave: 'Brave',\n    outscraper: 'Outscraper',\n    gemini: 'Gemini',\n  }\n  return labels[value.toLowerCase()] || value\n}\n")

    # Estilos para o novo estado parcial.
    rel = "frontend/src/styles.css"
    text = read(rel)
    if ".message-bar--warning" not in text:
        text = replace_once(
            text,
            ".message-bar--error { border-color:rgba(255,127,139,.25); background:rgba(128,39,50,.12); }\n.message-bar > svg { color:var(--danger); font-size:19px; }",
            ".message-bar--error { border-color:rgba(255,127,139,.25); background:rgba(128,39,50,.12); }\n.message-bar--warning { border-color:rgba(247,190,73,.22); background:rgba(113,79,20,.11); }\n.message-bar > svg { font-size:19px; }\n.message-bar--error > svg { color:var(--danger); }\n.message-bar--warning > svg { color:var(--warning); }",
            "frontend warning style",
        )
    text = text.replace(
        ".run-state--completed { color:var(--success); }.run-state--partial_budget{color:var(--warning)}.run-state--cancelled,.run-state--failed{color:var(--danger)}",
        ".run-state--completed { color:var(--success); }.run-state--partial_budget,.run-state--partial_results{color:var(--warning)}.run-state--cancelled,.run-state--failed{color:var(--danger)}",
    )
    write(rel, text)

    write("tests/test_phase841_fulfillment.py", 'from __future__ import annotations\n\nimport unittest\n\nfrom leadflow_agent.agent import LeadResearchAgent\nfrom leadflow_agent.models import Lead, SearchGoal\nfrom leadflow_agent.runtime import RunStatus\nfrom leadflow_agent.search_service import SearchRequest\n\n\nclass _OneLeadLocal:\n    name = "one-lead"\n\n    def search_places(self, query, goal, *, count=20):\n        return [\n            Lead(\n                name="Empresa Única",\n                city=goal.city,\n                state=goal.state,\n                phone="13 99999-1111",\n                source_provider=self.name,\n                discovered_query=query,\n            )\n        ]\n\n\nclass Phase841FulfillmentTests(unittest.TestCase):\n    def test_quota_fulfillment_is_enabled_by_default(self):\n        request = SearchRequest(segment="marcenaria", city="Praia Grande")\n        self.assertTrue(request.fulfill_quota)\n        self.assertGreaterEqual(request.max_queries, 10)\n        self.assertGreaterEqual(request.filter_pool_multiplier, 5)\n\n    def test_shortfall_is_not_reported_as_completed(self):\n        agent = LeadResearchAgent(local_search=_OneLeadLocal())\n        report = agent.research(\n            SearchGoal(segment="segmento muito específico", city="Praia Grande", state="SP", limit=2),\n            max_queries=1,\n        )\n        self.assertEqual(len(report.leads), 1)\n        self.assertEqual(report.run_status, RunStatus.PARTIAL_RESULTS.value)\n        self.assertIn("1/2", report.run_stop_reason or "")\n\n\nif __name__ == "__main__":\n    unittest.main()\n')

    # Validação sintática Python antes de encerrar.
    for rel in (
        "leadflow_agent/runtime.py",
        "leadflow_agent/agent.py",
        "leadflow_agent/search_service.py",
        "leadflow_agent/api.py",
        "leadflow_agent/planner.py",
        "tests/test_phase841_fulfillment.py",
    ):
        compile(read(rel), rel, "exec")

except Exception as exc:
    rollback()
    print(f"\n[ERRO] Phase 8.4.1 não foi aplicada. Alterações revertidas.\n{exc}")
    sys.exit(1)

print("\nPhase 8.4.1 aplicada com sucesso.")
print("Incluído:")
print("  - tentativa de completar a quantidade solicitada")
print("  - status partial_results quando a quota não puder ser preenchida")
print("  - frontend alinhado a 10 queries / pool 5x")
print("  - interface em Português do Brasil")
print("\nAgora rode:")
print("  python -m unittest discover -s tests -v")
print("  git diff --check")
print("  cd frontend")
print("  npm run typecheck")
print("  npm run build")
