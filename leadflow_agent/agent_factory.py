from __future__ import annotations

from .agent import LeadResearchAgent
from .cache import CachedWebSearchProvider, PersistentSearchCache
from .config import Settings
from .memory import LeadMemory
from .providers.brave import BraveSearchProvider
from .providers.gemini import GeminiPlannerProvider
from .providers.guarded import GuardedAIProvider, GuardedLocalSearchProvider, GuardedWebSearchProvider
from .providers.outscraper import OutscraperSearchProvider
from .providers.tavily import TavilySearchProvider
from .runtime import RunController
from .services.browser_auditor import BrowserAuditor
from .services.investigator import LeadInvestigator
from .services.visual_auditor import VisualAuditor
from .services.website_auditor import WebsiteAuditor


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
    """Build a research agent without coupling callers to the CLI layer."""

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

    if provider_name == "tavily" or (provider_name == "auto" and settings.tavily_api_key):
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY não configurada.")
        web = cached(GuardedWebSearchProvider(TavilySearchProvider(settings.tavily_api_key), controller))
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
            run_controller=controller,
        )

    if provider_name == "outscraper" or (provider_name == "auto" and settings.outscraper_api_key):
        if not settings.outscraper_api_key:
            raise RuntimeError("OUTSCRAPER_API_KEY não configurada.")
        local = GuardedLocalSearchProvider(OutscraperSearchProvider(settings.outscraper_api_key), controller)
        web_base = (
            GuardedWebSearchProvider(TavilySearchProvider(settings.tavily_api_key), controller)
            if settings.tavily_api_key
            else (
                GuardedWebSearchProvider(BraveSearchProvider(settings.brave_api_key), controller)
                if settings.brave_api_key
                else None
            )
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
            run_controller=controller,
        )

    if provider_name == "brave" or (provider_name == "auto" and settings.brave_api_key):
        if not settings.brave_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada.")
        provider = BraveSearchProvider(settings.brave_api_key)
        local = GuardedLocalSearchProvider(provider, controller)
        web = cached(GuardedWebSearchProvider(provider, controller))
        investigator = LeadInvestigator(web_search=web, extractor=llm) if llm is not None else None
        return "brave", LeadResearchAgent(
            local_search=local,
            web_search=web,
            llm=llm,
            investigator=investigator,
            lead_memory=memory,
            website_auditor=WebsiteAuditor(),
            browser_auditor=BrowserAuditor(),
            visual_auditor=VisualAuditor(llm) if llm is not None else None,
            run_controller=controller,
        )

    raise RuntimeError("Nenhum provider de busca configurado. Rode `python -m leadflow_agent setup`.")
