from __future__ import annotations

from dataclasses import dataclass

from .filters import LeadFilterSpec, Presence, Readiness
from .models import OpportunityType, WebsiteStatus


@dataclass(frozen=True, slots=True)
class SearchProfile:
    slug: str
    label: str
    description: str
    website_states: tuple[WebsiteStatus, ...] = ()
    instagram: Presence = Presence.ANY
    phone: Presence = Presence.ANY
    readiness: Readiness = Readiness.ANY
    opportunity_types: tuple[OpportunityType, ...] = ()
    min_opportunity_score: int | None = None
    max_visual_score: int | None = None
    require_any_contact: bool = False

    def filters(self) -> LeadFilterSpec:
        return LeadFilterSpec(
            website_states=set(self.website_states),
            instagram=self.instagram,
            phone=self.phone,
            readiness=self.readiness,
            opportunity_types=set(self.opportunity_types),
            min_opportunity_score=self.min_opportunity_score,
            max_visual_score=self.max_visual_score,
            require_any_contact=self.require_any_contact,
        )


PROFILES: dict[str, SearchProfile] = {
    "balanced": SearchProfile(
        "balanced", "Balanced", "Sem filtros rígidos; ranking padrão do LeadFlow.",
    ),
    "website-sales": SearchProfile(
        "website-sales", "Website Sales", "Oportunidades de primeiro site, rebuild, redesign ou otimização.",
        opportunity_types=(OpportunityType.NEW_SITE, OpportunityType.REBUILD, OpportunityType.REDESIGN, OpportunityType.OPTIMIZATION),
        min_opportunity_score=35,
        require_any_contact=True,
    ),
    "new-site": SearchProfile(
        "new-site", "New Website", "Empresas verificadas sem site e prontas para abordagem.",
        website_states=(WebsiteStatus.NOT_FOUND,), readiness=Readiness.READY, require_any_contact=True,
    ),
    "redesign": SearchProfile(
        "redesign", "Redesign", "Empresas com oportunidade de rebuild/redesign/otimização.",
        opportunity_types=(OpportunityType.REBUILD, OpportunityType.REDESIGN, OpportunityType.OPTIMIZATION),
        require_any_contact=True,
    ),
    "visual-redesign": SearchProfile(
        "visual-redesign", "Visual Redesign", "Sites com análise visual disponível e score visual <= 60.",
        opportunity_types=(OpportunityType.REDESIGN, OpportunityType.OPTIMIZATION, OpportunityType.REBUILD),
        max_visual_score=60,
        require_any_contact=True,
    ),
    "ready-only": SearchProfile(
        "ready-only", "Ready Only", "Somente leads com identidade suficientemente confirmada para abordagem.",
        readiness=Readiness.READY,
    ),
    "instagram-first": SearchProfile(
        "instagram-first", "Instagram First", "Leads com Instagram, úteis para prospecção via DM.",
        instagram=Presence.PRESENT,
    ),
    "phone-first": SearchProfile(
        "phone-first", "Phone First", "Leads com telefone disponível.",
        phone=Presence.PRESENT,
    ),
}


def get_profile(slug: str) -> SearchProfile:
    try:
        return PROFILES[slug]
    except KeyError as exc:
        raise ValueError(f"Perfil desconhecido: {slug}") from exc
