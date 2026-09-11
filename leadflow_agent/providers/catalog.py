from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    slug: str
    label: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...]
    byok: bool = True


PROVIDER_CATALOG: dict[str, ProviderDescriptor] = {
    "tavily": ProviderDescriptor(
        slug="tavily",
        label="Tavily",
        roles=("web_search",),
        capabilities=("web_evidence", "usage_validation", "persistent_cache"),
    ),
    "brave": ProviderDescriptor(
        slug="brave",
        label="Brave Search",
        roles=("web_search", "local_search"),
        capabilities=("web_evidence", "local_business_results"),
    ),
    "outscraper": ProviderDescriptor(
        slug="outscraper",
        label="Outscraper",
        roles=("local_search",),
        capabilities=("local_business_results",),
    ),
    "gemini": ProviderDescriptor(
        slug="gemini",
        label="Gemini",
        roles=("planner", "extractor", "visual_analysis"),
        capabilities=("query_planning", "structured_extraction", "multimodal_visual_analysis"),
    ),
}
