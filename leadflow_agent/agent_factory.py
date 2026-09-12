from __future__ import annotations

from .agent import LeadResearchAgent
from .cache import CachedWebSearchProvider, PersistentSearchCache
from .config import Settings
from .memory import LeadMemory
from .providers.brave import BraveSearchProvider
from .providers.gemini import GeminiPlannerProvider
from .providers.guarded import GuardedAIProvider, GuardedLocalSearchProvider, GuardedWebSearchProvider
from .providers.multi import RoundRobinLocalSearchProvider, RoundRobinWebSearchProvider
from .providers.outscraper import OutscraperSearchProvider
from .providers.tavily import TavilySearchProvider
from .runtime import RunController
from .services.browser_auditor import BrowserAuditor
from .services.investigator import LeadInvestigator
from .services.visual_auditor import VisualAuditor
from .services.website_auditor import WebsiteAuditor


def _one_or_multi_web(providers):
    providers = [item for item in providers if item is not None]
    if not providers:
        return None
    return providers[0] if len(providers) == 1 else RoundRobinWebSearchProvider(providers)


def _one_or_multi_local(providers):
    providers = [item for item in providers if item is not None]
    if not providers:
        return None
    return providers[0] if len(providers) == 1 else RoundRobinLocalSearchProvider(providers)


def build_agent(
    settings: Settings,
    *,
    no_ai: bool,
    provider_name: str,
    use_cache: bool = True,
    refresh_cache: bool = False,
    cache_ttl_days: int = 14,
    use_memory: bool = True,
    run_controller: RunController | None = None,
):
    """Build a research agent without coupling callers to the CLI layer.

    ``auto`` is capability-based: every configured discovery source can
    contribute. Explicit provider selection remains deterministic and uses only
    that provider for discovery.
    """

    controller = run_controller or RunController()
    llm = None
    if not no_ai and settings.gemini_api_key:
        llm = GuardedAIProvider(
            GeminiPlannerProvider(settings.gemini_api_key, model=settings.gemini_model),
            controller,
        )

    memory = LeadMemory(settings.db_path) if use_memory else None

    def cached(provider):
        if provider is None or not use_cache:
            return provider
        return CachedWebSearchProvider(
            provider,
            PersistentSearchCache(settings.db_path, ttl_days=cache_ttl_days),
            force_refresh=refresh_cache,
        )

    def make_agent(*, local=None, web=None):
        investigator = LeadInvestigator(web_search=web, extractor=llm) if (web is not None and llm is not None) else None
        return LeadResearchAgent(
            local_search=local,
            web_search=web,
            llm=llm,
            lead_extractor=llm,
            investigator=investigator,
            lead_memory=memory,
            website_auditor=WebsiteAuditor(),
            browser_auditor=BrowserAuditor(),
            visual_auditor=VisualAuditor(llm) if llm is not None else None,
            run_controller=controller,
        )

    if provider_name == "auto":
        local_sources = []
        web_sources = []
        labels: list[str] = []

        if settings.outscraper_api_key:
            local_sources.append(
                GuardedLocalSearchProvider(
                    OutscraperSearchProvider(settings.outscraper_api_key),
                    controller,
                )
            )
            labels.append("outscraper")

        brave_base = None
        if settings.brave_api_key:
            brave_base = BraveSearchProvider(settings.brave_api_key)
            local_sources.append(GuardedLocalSearchProvider(brave_base, controller))
            web_sources.append(cached(GuardedWebSearchProvider(brave_base, controller)))
            labels.append("brave")

        if settings.tavily_api_key:
            web_sources.insert(
                0,
                cached(
                    GuardedWebSearchProvider(
                        TavilySearchProvider(settings.tavily_api_key),
                        controller,
                    )
                ),
            )
            labels.insert(0, "tavily")

        local = _one_or_multi_local(local_sources)
        web = _one_or_multi_web(web_sources)
        if local is None and web is None:
            raise RuntimeError("Nenhum provedor de busca configurado. Rode `python -m leadflow_agent setup`.")

        label = "+".join(dict.fromkeys(labels))
        return label, make_agent(local=local, web=web)

    if provider_name == "tavily":
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY não configurada.")
        web = cached(
            GuardedWebSearchProvider(
                TavilySearchProvider(settings.tavily_api_key),
                controller,
            )
        )
        return "tavily", make_agent(web=web)

    if provider_name == "outscraper":
        if not settings.outscraper_api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY não configurada.")
        local = GuardedLocalSearchProvider(
            OutscraperSearchProvider(settings.outscraper_api_key),
            controller,
        )
        web_base = (
            GuardedWebSearchProvider(TavilySearchProvider(settings.tavily_api_key), controller)
            if settings.tavily_api_key
            else (
                GuardedWebSearchProvider(BraveSearchProvider(settings.brave_api_key), controller)
                if settings.brave_api_key
                else None
            )
        )
        return "outscraper", make_agent(local=local, web=cached(web_base))

    if provider_name == "brave":
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada.")
        provider = BraveSearchProvider(settings.brave_api_key)
        local = GuardedLocalSearchProvider(provider, controller)
        web = cached(GuardedWebSearchProvider(provider, controller))
        return "brave", make_agent(local=local, web=web)

    raise RuntimeError(f"Provedor desconhecido: {provider_name}")
