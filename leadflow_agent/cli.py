from __future__ import annotations

import argparse
import getpass
import importlib.util
import sys
from pathlib import Path

from .agent import LeadResearchAgent
from .cache import CachedWebSearchProvider, PersistentSearchCache
from .config import Settings
from .export import export_report
from .models import SearchGoal
from .memory import LeadMemory
from .providers.brave import BraveSearchProvider
from .providers.gemini import GeminiPlannerProvider
from .providers.outscraper import OutscraperSearchProvider
from .providers.tavily import TavilySearchProvider
from .storage import LeadStore
from .services.investigator import LeadInvestigator
from .services.website_auditor import WebsiteAuditor
from .services.browser_auditor import BrowserAuditor
from .services.visual_auditor import VisualAuditor


VERSION = "0.1.4-dev"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leadflow",
        description="LeadFlow Agent — IA como cérebro, busca web como olhos.",
    )
    parser.add_argument("--version", action="version", version=f"LeadFlow Agent {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Valida Gemini e providers BYOK sem expor chaves.")
    doctor.add_argument("--offline", action="store_true", help="Não faz validações de rede.")
    sub.add_parser("setup", help="Cria um .env local de forma interativa.")

    search = sub.add_parser("search", help="Pesquisa leads reais.")
    search.add_argument("--segment", required=True, help='Ex.: "marcenaria"')
    search.add_argument("--city", required=True, help='Ex.: "Praia Grande"')
    search.add_argument("--state", default="", help='Ex.: "SP"')
    search.add_argument("--country", default="Brazil")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--max-queries", type=int, default=6)
    search.add_argument("--require-phone", action="store_true")
    search.add_argument("--enrich-web", action="store_true", help="Faz buscas extras por empresa para site/social.")
    search.add_argument("--enrichment-limit", type=int, default=None)
    search.add_argument(
        "--investigate",
        action="store_true",
        help="Investiga leads individualmente com buscas extras e entity resolution.",
    )
    search.add_argument(
        "--investigation-limit",
        type=int,
        default=3,
        help="Máximo de leads investigados nesta execução (default: 3).",
    )
    search.add_argument(
        "--investigation-budget",
        type=int,
        default=2,
        help="Buscas web por lead investigado, de 1 a 3 (default: 2).",
    )
    search.add_argument(
        "--cache-ttl-days",
        type=int,
        default=14,
        help="Validade do cache de busca web em dias, de 1 a 90 (default: 14).",
    )
    search.add_argument(
        "--no-cache",
        action="store_true",
        help="Desliga o cache persistente de buscas web para esta execução.",
    )
    search.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignora entradas existentes, faz buscas reais e atualiza o cache.",
    )
    search.add_argument(
        "--no-memory",
        action="store_true",
        help="Não reutiliza campos/rejeições verificados em pesquisas anteriores.",
    )
    search.add_argument(
        "--audit-websites",
        action="store_true",
        help="Audita tecnicamente sites encontrados sem consumir Tavily/Gemini.",
    )
    search.add_argument(
        "--audit-limit",
        type=int,
        default=3,
        help="Máximo de sites auditados nesta execução (default: 3).",
    )
    search.add_argument(
        "--audit-timeout",
        type=float,
        default=8.0,
        help="Timeout por site em segundos, de 2 a 20 (default: 8).",
    )
    search.add_argument(
        "--audit-ttl-days",
        type=int,
        default=7,
        help="Validade de uma auditoria salva, de 1 a 30 dias (default: 7).",
    )
    search.add_argument(
        "--refresh-audits",
        action="store_true",
        help="Refaz auditorias mesmo quando existe resultado recente em memória.",
    )
    search.add_argument(
        "--browser-audit",
        action="store_true",
        help="Usa Chromium/Playwright para medir mobile/CTA/erros e capturar screenshots.",
    )
    search.add_argument(
        "--browser-audit-limit",
        type=int,
        default=3,
        help="Máximo de sites auditados em navegador real (default: 3).",
    )
    search.add_argument(
        "--browser-timeout",
        type=float,
        default=12.0,
        help="Timeout por site no navegador, de 4 a 30 segundos (default: 12).",
    )
    search.add_argument(
        "--browser-audit-ttl-days",
        type=int,
        default=7,
        help="Validade da auditoria de navegador, de 1 a 30 dias (default: 7).",
    )
    search.add_argument(
        "--refresh-browser-audits",
        action="store_true",
        help="Refaz auditorias de navegador mesmo quando existe resultado recente.",
    )
    search.add_argument(
        "--visual-audit",
        action="store_true",
        help="Usa Gemini multimodal sobre screenshots desktop/mobile para avaliar qualidade visual.",
    )
    search.add_argument(
        "--visual-audit-limit",
        type=int,
        default=3,
        help="Máximo de sites avaliados visualmente por IA (default: 3).",
    )
    search.add_argument(
        "--visual-audit-ttl-days",
        type=int,
        default=14,
        help="Validade da análise visual, de 1 a 30 dias (default: 14).",
    )
    search.add_argument(
        "--refresh-visual-audits",
        action="store_true",
        help="Refaz análises visuais mesmo quando existe resultado recente.",
    )
    search.add_argument("--no-ai", action="store_true", help="Desliga Gemini; Tavily usa extração heurística conservadora.")
    search.add_argument(
        "--provider",
        choices=["auto", "tavily", "outscraper", "brave"],
        default="auto",
        help="Provider de descoberta. Auto prioriza Tavily.",
    )
    search.add_argument("--no-save", action="store_true", help="Não grava no SQLite.")
    return parser


def _write_env_interactive(path: Path) -> int:
    print("LeadFlow setup (BYOK) — Agent architecture v0.1.4-dev")
    print("Gemini = cérebro/extrator. Tavily = busca web. As chaves ficam só no .env local.\n")
    gemini = getpass.getpass("Gemini API key (recomendada): ").strip()
    model = input("Gemini model [gemini-3.1-flash-lite]: ").strip() or "gemini-3.1-flash-lite"
    tavily = getpass.getpass("Tavily API key (provider recomendado): ").strip()
    brave = getpass.getpass("Brave Search API key (opcional; Enter para pular): ").strip()
    outscraper = getpass.getpass("Outscraper API key (opcional/legado; Enter para pular): ").strip()
    db = input("SQLite database [leadflow.db]: ").strip() or "leadflow.db"
    content = (
        f"GEMINI_API_KEY={gemini}\n"
        f"GEMINI_MODEL={model}\n"
        f"TAVILY_API_KEY={tavily}\n"
        f"BRAVE_SEARCH_API_KEY={brave}\n"
        f"OUTSCRAPER_API_KEY={outscraper}\n"
        f"LEADFLOW_DB={db}\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"\nConfiguração salva em: {path.resolve()}")
    print("Não faça commit do .env.")
    if not tavily and not brave and not outscraper:
        print("\nATENÇÃO: nenhum provider de busca foi configurado.")
    return 0


def _doctor(settings: Settings, *, offline: bool = False) -> int:
    print("LeadFlow Agent Doctor")
    print("---------------------")
    print(f"Python:       {sys.version.split()[0]}")
    print(f"Gemini key:   {'configurada' if settings.gemini_api_key else 'não configurada'}")
    print(f"Gemini model: {settings.gemini_model}")
    print(f"Tavily:       {'configurada' if settings.tavily_api_key else 'não configurada'}")
    print(f"Brave:        {'configurada' if settings.brave_api_key else 'não configurada'}")
    print(f"Outscraper:   {'configurada' if settings.outscraper_api_key else 'não configurada'}")
    print(f"Database:     {Path(settings.db_path).resolve()}")
    print(f"Playwright:   {'instalado' if importlib.util.find_spec('playwright') else 'opcional/não instalado'}")

    failures = 0
    if not offline and settings.gemini_api_key:
        provider = GeminiPlannerProvider(settings.gemini_api_key, model=settings.gemini_model)
        ok, detail = provider.validate_key(live_generation=True)
        print(f"Gemini geração: {'OK' if ok else 'FALHOU'}")
        if not ok:
            print(f"  {detail}")
            failures += 1

    if not offline and settings.tavily_api_key:
        provider = TavilySearchProvider(settings.tavily_api_key)
        ok, detail = provider.validate_key()
        print(f"Tavily API:     {'OK' if ok else 'FALHOU'}")
        print(f"  {detail}")
        if not ok:
            failures += 1

    if not offline and settings.brave_api_key:
        provider = BraveSearchProvider(settings.brave_api_key)
        ok, detail = provider.validate_key()
        print(f"Brave API:      {'OK' if ok else 'FALHOU'}")
        if not ok:
            print(f"  {detail}")
            failures += 1

    if not offline and settings.outscraper_api_key:
        provider = OutscraperSearchProvider(settings.outscraper_api_key)
        ok, detail = provider.validate_key()
        print(f"Outscraper API: {'OK' if ok else 'FALHOU'}")
        if not ok:
            print(f"  {detail}")
            failures += 1

    if not settings.tavily_api_key and not settings.brave_api_key and not settings.outscraper_api_key:
        print("\nSEM PROVIDER DE BUSCA: configure TAVILY_API_KEY, BRAVE_SEARCH_API_KEY ou OUTSCRAPER_API_KEY.")
        return 1
    if failures:
        return 1

    print("\nOK: pronto para uma busca real.")
    if settings.tavily_api_key:
        print("Caminho recomendado: Tavily (evidências) + Gemini (extração/planejamento).")
    return 0


def _build_agent(
    settings: Settings,
    *,
    no_ai: bool,
    provider_name: str,
    use_cache: bool = True,
    refresh_cache: bool = False,
    cache_ttl_days: int = 14,
    use_memory: bool = True,
):
    llm = None
    if not no_ai and settings.gemini_api_key:
        llm = GeminiPlannerProvider(settings.gemini_api_key, model=settings.gemini_model)

    memory = LeadMemory(settings.db_path) if use_memory else None

    def cached(provider):
        if provider is None or not use_cache:
            return provider
        return CachedWebSearchProvider(
            provider,
            PersistentSearchCache(settings.db_path, ttl_days=cache_ttl_days),
            force_refresh=refresh_cache,
        )

    if provider_name == "tavily" or (provider_name == "auto" and settings.tavily_api_key):
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY não configurada.")
        web = cached(TavilySearchProvider(settings.tavily_api_key))
        investigator = LeadInvestigator(web_search=web, extractor=llm) if llm is not None else None
        return "tavily", LeadResearchAgent(
            web_search=web,
            llm=llm,
            lead_extractor=llm,
            investigator=investigator,
            lead_memory=memory,
            website_auditor=WebsiteAuditor(),
            browser_auditor=BrowserAuditor(),
            visual_auditor=VisualAuditor(llm) if llm is not None else None,
        )

    if provider_name == "outscraper" or (provider_name == "auto" and settings.outscraper_api_key):
        if not settings.outscraper_api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY não configurada.")
        local = OutscraperSearchProvider(settings.outscraper_api_key)
        web_base = TavilySearchProvider(settings.tavily_api_key) if settings.tavily_api_key else (
            BraveSearchProvider(settings.brave_api_key) if settings.brave_api_key else None
        )
        web = cached(web_base)
        investigator = LeadInvestigator(web_search=web, extractor=llm) if (web is not None and llm is not None) else None
        return "outscraper", LeadResearchAgent(
            local_search=local,
            web_search=web,
            llm=llm,
            investigator=investigator,
            lead_memory=memory,
            website_auditor=WebsiteAuditor(),
            browser_auditor=BrowserAuditor(),
            visual_auditor=VisualAuditor(llm) if llm is not None else None,
        )

    if provider_name == "brave" or (provider_name == "auto" and settings.brave_api_key):
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada.")
        provider = BraveSearchProvider(settings.brave_api_key)
        web = cached(provider)
        investigator = LeadInvestigator(web_search=web, extractor=llm) if llm is not None else None
        return "brave", LeadResearchAgent(
            local_search=provider,
            web_search=web,
            llm=llm,
            investigator=investigator,
            lead_memory=memory,
            website_auditor=WebsiteAuditor(),
            browser_auditor=BrowserAuditor(),
            visual_auditor=VisualAuditor(llm) if llm is not None else None,
        )

    raise RuntimeError("Nenhum provider de busca configurado. Rode `python -m leadflow_agent setup`.")


def _search(args: argparse.Namespace, settings: Settings) -> int:
    if args.limit < 1 or args.limit > 1000:
        print("--limit deve ficar entre 1 e 1000.", file=sys.stderr)
        return 2
    if args.investigation_budget < 1 or args.investigation_budget > 3:
        print("--investigation-budget deve ficar entre 1 e 3.", file=sys.stderr)
        return 2
    if args.investigation_limit < 0:
        print("--investigation-limit não pode ser negativo.", file=sys.stderr)
        return 2
    if args.audit_limit < 0:
        print("--audit-limit não pode ser negativo.", file=sys.stderr)
        return 2
    if args.audit_timeout < 2 or args.audit_timeout > 20:
        print("--audit-timeout deve ficar entre 2 e 20 segundos.", file=sys.stderr)
        return 2
    if args.audit_ttl_days < 1 or args.audit_ttl_days > 30:
        print("--audit-ttl-days deve ficar entre 1 e 30.", file=sys.stderr)
        return 2
    if args.browser_audit_limit < 0:
        print("--browser-audit-limit não pode ser negativo.", file=sys.stderr)
        return 2
    if args.browser_timeout < 4 or args.browser_timeout > 30:
        print("--browser-timeout deve ficar entre 4 e 30 segundos.", file=sys.stderr)
        return 2
    if args.browser_audit_ttl_days < 1 or args.browser_audit_ttl_days > 30:
        print("--browser-audit-ttl-days deve ficar entre 1 e 30.", file=sys.stderr)
        return 2
    if args.visual_audit_limit < 0:
        print("--visual-audit-limit não pode ser negativo.", file=sys.stderr)
        return 2
    if args.visual_audit_ttl_days < 1 or args.visual_audit_ttl_days > 30:
        print("--visual-audit-ttl-days deve ficar entre 1 e 30.", file=sys.stderr)
        return 2
    if args.visual_audit and (args.no_ai or not settings.gemini_api_key):
        print("--visual-audit requer Gemini configurado.", file=sys.stderr)
        return 2
    if args.cache_ttl_days < 1 or args.cache_ttl_days > 90:
        print("--cache-ttl-days deve ficar entre 1 e 90.", file=sys.stderr)
        return 2
    if args.no_cache and args.refresh_cache:
        print("--no-cache e --refresh-cache não podem ser usados juntos.", file=sys.stderr)
        return 2
    if args.investigate and (args.no_ai or not settings.gemini_api_key):
        print("--investigate requer Gemini configurado; a investigação não usa heurística insegura.", file=sys.stderr)
        return 2

    try:
        selected, agent = _build_agent(
            settings,
            no_ai=args.no_ai,
            provider_name=args.provider,
            use_cache=not args.no_cache,
            refresh_cache=args.refresh_cache,
            cache_ttl_days=args.cache_ttl_days,
            use_memory=not args.no_memory,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    goal = SearchGoal(
        segment=args.segment,
        city=args.city,
        state=args.state,
        country=args.country,
        limit=args.limit,
        require_phone=args.require_phone,
        prefer_no_website=True,
    )

    ai_mode = "Gemini" if (settings.gemini_api_key and not args.no_ai) else "Basic"
    print(f"Meta: encontrar {goal.limit} leads para '{goal.segment}' em {goal.location_label}")
    print(f"Cérebro/extrator: {ai_mode}")
    print(f"Busca: {selected}")
    if args.no_cache:
        print("Cache de busca: DESLIGADO")
    elif args.refresh_cache:
        print(f"Cache de busca: REFRESH forçado | TTL {args.cache_ttl_days} dias")
    else:
        print(f"Cache de busca: ATIVO | TTL {args.cache_ttl_days} dias")
    print(f"Memória de leads: {'DESLIGADA' if args.no_memory else 'ATIVA'}")
    if selected == "tavily":
        print("Fluxo: Tavily encontra evidências → Gemini extrai empresas → LeadFlow deduplica.")
    if args.enrich_web:
        print("Enriquecimento web legado: ATIVO (pode consumir buscas extras)")
    if args.investigate:
        possible = min(goal.limit, args.investigation_limit)
        max_searches = possible * args.investigation_budget
        print(
            f"Investigator: ATIVO — até {possible} leads × {args.investigation_budget} buscas "
            f"(máximo {max_searches} buscas extras)"
        )
    if args.audit_websites:
        print(
            f"Website audit: ATIVO — até {args.audit_limit} sites | "
            f"TTL {args.audit_ttl_days} dias | timeout {args.audit_timeout:g}s"
        )
    if args.browser_audit:
        print(
            f"Browser/UX audit: ATIVO — até {args.browser_audit_limit} sites | "
            f"TTL {args.browser_audit_ttl_days} dias | timeout {args.browser_timeout:g}s"
        )
    if args.visual_audit:
        print(
            f"Visual audit: ATIVO — até {args.visual_audit_limit} sites | "
            f"TTL {args.visual_audit_ttl_days} dias | Gemini multimodal"
        )
    print()

    report = agent.research(
        goal,
        max_queries=args.max_queries,
        enrich_web=args.enrich_web,
        enrichment_limit=args.enrichment_limit,
        investigate=args.investigate,
        investigation_limit=args.investigation_limit,
        investigation_budget=args.investigation_budget,
        audit_websites=args.audit_websites,
        audit_limit=args.audit_limit,
        audit_timeout=args.audit_timeout,
        audit_ttl_days=args.audit_ttl_days,
        refresh_audits=args.refresh_audits,
        browser_audit=args.browser_audit,
        browser_audit_limit=args.browser_audit_limit,
        browser_timeout=args.browser_timeout,
        browser_audit_ttl_days=args.browser_audit_ttl_days,
        refresh_browser_audits=args.refresh_browser_audits,
        visual_audit=args.visual_audit,
        visual_audit_limit=args.visual_audit_limit,
        visual_audit_ttl_days=args.visual_audit_ttl_days,
        refresh_visual_audits=args.refresh_visual_audits,
    )

    print(f"Planner: {report.plan.generated_by}")
    if report.plan.rationale:
        print(f"Motivo: {report.plan.rationale}")
    print("Consultas planejadas:")
    for q in report.plan.queries:
        marker = "✓" if q in report.queries_executed else "·"
        print(f"  {marker} {q}")
    print()
    print(f"Resultados-fonte vistos:   {report.local_results_seen}")
    print(f"Duplicatas removidas:      {report.duplicates_removed}")
    print(f"Leads entregues:           {len(report.leads)} / {goal.limit}")
    if report.quality_rejected:
        print(f"Candidatos descartados:    {report.quality_rejected} (quality gate)")
    if report.invalid_fields_removed:
        print(f"Campos inválidos removidos:{report.invalid_fields_removed:>5}")
    if args.investigate:
        print(f"Leads investigados:        {report.investigated_leads}")
        print(f"Buscas de investigação:    {report.investigation_searches}")
    if args.audit_websites:
        print(f"Sites auditados agora:      {report.website_audits_run}")
        print(f"Auditorias reutilizadas:    {report.website_audits_reused}")
        print(f"Falhas/bloqueios de audit:  {report.website_audit_errors}")
    if args.browser_audit:
        print(f"Browser audits agora:        {report.browser_audits_run}")
        print(f"Browser audits reutilizados: {report.browser_audits_reused}")
        print(f"Falhas de browser audit:     {report.browser_audit_errors}")
    if args.visual_audit:
        print(f"Visual audits agora:         {report.visual_audits_run}")
        print(f"Visual audits reutilizados:  {report.visual_audits_reused}")
        print(f"Falhas/baixa confiança visual:{report.visual_audit_errors:>3}")
    if not args.no_cache:
        print(f"Cache hits (buscas poupadas): {report.search_cache_hits}")
        print(f"Cache misses (calls reais):   {report.search_cache_misses}")
        print(f"Entradas gravadas no cache:   {report.search_cache_writes}")
    if not args.no_memory:
        print(f"Memórias reaproveitadas:      {report.memory_hits}")
        print(f"Campos restaurados:           {report.memory_fields_restored}")
        print(f"Rejeições restauradas:        {report.memory_rejections_restored}")
    if report.errors:
        print(f"Erros recuperáveis:        {len(report.errors)}")
        for error in report.errors[:6]:
            print(f"  ! {error}")
    print()

    if not report.leads:
        print("Nenhum lead válido foi encontrado.")
        return 3

    print("TOP LEADS")
    print("---------")
    for idx, lead in enumerate(report.leads, start=1):
        if lead.website:
            web = lead.website
        elif lead.website_status.value == "not_found":
            web = "sem site (verificado)"
        elif lead.website_status.value == "unreachable":
            web = "site indisponível"
        else:
            web = "site ainda não verificado"
        phone = lead.phone or "sem telefone"
        reviews = f"{lead.review_count} reviews" if lead.review_count is not None else "reviews ?"
        opp_type = lead.opportunity.type.value if lead.opportunity else "unknown"
        action = "READY" if lead.opportunity and lead.opportunity.actionable else "VERIFY"
        print(
            f"{idx:>2}. [opp {lead.score:>3} | conf {lead.confidence_score:>3} | "
            f"{opp_type} | {action}] {lead.name}"
        )
        print(f"    {phone} | {web} | {reviews}")
        if lead.address:
            print(f"    {lead.address}")
        if lead.socials:
            print(f"    Social: {lead.socials[0]}")
        if lead.provider_url:
            print(f"    Evidência: {lead.provider_url}")
        if args.investigate:
            print(
                f"    Identidade: {lead.identity_status.value} "
                f"({lead.identity_confidence:.0%}) | "
                f"site: {lead.website_status.value}"
            )
        if args.audit_websites and lead.website_audit is not None:
            audit = lead.website_audit
            status = audit.status_code if audit.status_code is not None else "-"
            latency = f"{audit.response_time_ms}ms" if audit.response_time_ms is not None else "-"
            print(
                f"    Audit: {audit.technical_score}/100 | HTTP {status} | "
                f"HTTPS {'sim' if audit.uses_https else 'não'} | {latency}"
            )
            if audit.findings:
                print(f"    Audit findings: {'; '.join(audit.findings[:2])}")
        if args.browser_audit and lead.browser_audit is not None:
            browser = lead.browser_audit
            print(
                f"    Browser UX: {browser.ux_score}/100 | mobile overflow "
                f"{'sim' if browser.mobile_overflow else 'não'} | CTA visíveis {browser.visible_contact_cta_count}"
            )
            if browser.findings:
                print(f"    Browser findings: {'; '.join(browser.findings[:2])}")
            if browser.mobile_screenshot:
                print(f"    Mobile screenshot: {browser.mobile_screenshot}")
        if args.visual_audit and lead.visual_audit is not None:
            visual = lead.visual_audit
            print(
                f"    Visual: {visual.overall_score}/100 | desktop {visual.desktop_score} | "
                f"mobile {visual.mobile_score} | confiança {visual.confidence:.0%}"
            )
            if visual.weaknesses:
                print(f"    Visual findings: {'; '.join(visual.weaknesses[:2])}")
        if lead.opportunity is not None:
            print(f"    Oferta sugerida: {lead.opportunity.service_fit}")
            if lead.opportunity.reasons:
                print(f"    Opportunity: {lead.opportunity.reasons[-1]}")
            if lead.opportunity.cautions:
                print(f"    Atenção: {lead.opportunity.cautions[0]}")
        print(f"    via: {lead.discovered_query}")

    csv_path, json_path = export_report(report)
    print(f"\nCSV:  {csv_path.resolve()}")
    print(f"JSON: {json_path.resolve()}")

    if not args.no_save:
        store = LeadStore(settings.db_path)
        try:
            run_id = store.save_report(report)
            total = store.count_leads()
        finally:
            store.close()
        print(f"DB:   pesquisa #{run_id}; {total} leads únicos acumulados")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "setup":
        return _write_env_interactive(Path(".env"))

    settings = Settings.load()
    if args.command == "doctor":
        return _doctor(settings, offline=args.offline)
    if args.command == "search":
        return _search(args, settings)
    return 2
