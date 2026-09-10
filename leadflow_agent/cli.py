from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .agent import LeadResearchAgent
from .config import Settings
from .export import export_report
from .models import SearchGoal
from .providers.brave import BraveSearchProvider
from .providers.gemini import GeminiPlannerProvider
from .providers.outscraper import OutscraperSearchProvider
from .providers.tavily import TavilySearchProvider
from .storage import LeadStore


VERSION = "0.1.3"


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
    print("LeadFlow setup (BYOK) — Agent architecture v0.1.3")
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


def _build_agent(settings: Settings, *, no_ai: bool, provider_name: str):
    llm = None
    if not no_ai and settings.gemini_api_key:
        llm = GeminiPlannerProvider(settings.gemini_api_key, model=settings.gemini_model)

    if provider_name == "tavily" or (provider_name == "auto" and settings.tavily_api_key):
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY não configurada.")
        web = TavilySearchProvider(settings.tavily_api_key)
        return "tavily", LeadResearchAgent(
            web_search=web,
            llm=llm,
            lead_extractor=llm,
        )

    if provider_name == "outscraper" or (provider_name == "auto" and settings.outscraper_api_key):
        if not settings.outscraper_api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY não configurada.")
        local = OutscraperSearchProvider(settings.outscraper_api_key)
        web = TavilySearchProvider(settings.tavily_api_key) if settings.tavily_api_key else (
            BraveSearchProvider(settings.brave_api_key) if settings.brave_api_key else None
        )
        return "outscraper", LeadResearchAgent(local_search=local, web_search=web, llm=llm)

    if provider_name == "brave" or (provider_name == "auto" and settings.brave_api_key):
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada.")
        provider = BraveSearchProvider(settings.brave_api_key)
        return "brave", LeadResearchAgent(local_search=provider, web_search=provider, llm=llm)

    raise RuntimeError("Nenhum provider de busca configurado. Rode `python -m leadflow_agent setup`.")


def _search(args: argparse.Namespace, settings: Settings) -> int:
    if args.limit < 1 or args.limit > 1000:
        print("--limit deve ficar entre 1 e 1000.", file=sys.stderr)
        return 2

    try:
        selected, agent = _build_agent(settings, no_ai=args.no_ai, provider_name=args.provider)
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
    if selected == "tavily":
        print("Fluxo: Tavily encontra evidências → Gemini extrai empresas → LeadFlow deduplica.")
    if args.enrich_web:
        print("Enriquecimento web: ATIVO (pode consumir buscas extras)")
    print()

    report = agent.research(
        goal,
        max_queries=args.max_queries,
        enrich_web=args.enrich_web,
        enrichment_limit=args.enrichment_limit,
    )

    print(f"Planner: {report.plan.generated_by}")
    print("Consultas planejadas:")
    for q in report.plan.queries:
        marker = "✓" if q in report.queries_executed else "·"
        print(f"  {marker} {q}")
    print()
    print(f"Resultados-fonte vistos:   {report.local_results_seen}")
    print(f"Duplicatas removidas:      {report.duplicates_removed}")
    print(f"Leads entregues:           {len(report.leads)} / {goal.limit}")
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
        web = lead.website or "site não identificado"
        phone = lead.phone or "sem telefone"
        reviews = f"{lead.review_count} reviews" if lead.review_count is not None else "reviews ?"
        print(f"{idx:>2}. [{lead.score:>3}] {lead.name}")
        print(f"    {phone} | {web} | {reviews}")
        if lead.address:
            print(f"    {lead.address}")
        if lead.socials:
            print(f"    Social: {lead.socials[0]}")
        if lead.provider_url:
            print(f"    Evidência: {lead.provider_url}")
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
