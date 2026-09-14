from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True, slots=True)
class SegmentPreset:
    slug: str
    label: str
    category: str
    aliases: tuple[str, ...] = ()


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().strip().replace("-", " ").split())


SEGMENTS: tuple[SegmentPreset, ...] = (
    SegmentPreset("marcenaria", "marcenaria", "Casa & Construção", ("marceneiro", "moveis planejados", "móveis planejados")),
    SegmentPreset("vidracaria", "vidraçaria", "Casa & Construção", ("vidracaria", "vidros")),
    SegmentPreset("serralheria", "serralheria", "Casa & Construção", ("serralheiro",)),
    SegmentPreset("gesso-drywall", "gesso e drywall", "Casa & Construção", ("gesseiro", "drywall")),
    SegmentPreset("pintura", "pintura residencial", "Casa & Construção", ("pintor", "pintura predial")),
    SegmentPreset("eletricista", "eletricista", "Casa & Construção", ("eletrica residencial", "elétrica residencial")),
    SegmentPreset("encanador", "encanador", "Casa & Construção", ("hidraulica", "hidráulica")),
    SegmentPreset("ar-condicionado", "ar-condicionado", "Casa & Construção", ("climatizacao", "climatização")),
    SegmentPreset("impermeabilizacao", "impermeabilização", "Casa & Construção", ("impermeabilizacao",)),
    SegmentPreset("limpeza-estofados", "limpeza de estofados", "Casa & Construção", ("higienizacao de estofados", "higienização de estofados")),
    SegmentPreset("paisagismo", "paisagismo", "Casa & Construção", ("jardinagem", "jardineiro")),
    SegmentPreset("reformas", "reformas", "Casa & Construção", ("reforma residencial", "empreiteira")),

    SegmentPreset("oficina-mecanica", "oficina mecânica", "Automotivo", ("mecanica automotiva", "mecânica automotiva")),
    SegmentPreset("auto-eletrica", "auto elétrica", "Automotivo", ("auto eletrica",)),
    SegmentPreset("estetica-automotiva", "estética automotiva", "Automotivo", ("detailing", "estetica automotiva")),
    SegmentPreset("funilaria-pintura", "funilaria e pintura", "Automotivo", ("funilaria",)),
    SegmentPreset("pneus", "loja de pneus", "Automotivo", ("pneus", "centro automotivo")),

    SegmentPreset("barbearia", "barbearia", "Beleza & Bem-estar"),
    SegmentPreset("salao-beleza", "salão de beleza", "Beleza & Bem-estar", ("salao de beleza", "cabeleireiro")),
    SegmentPreset("estetica", "clínica de estética", "Beleza & Bem-estar", ("estetica", "estética")),
    SegmentPreset("manicure", "manicure e nail designer", "Beleza & Bem-estar", ("nail designer", "unhas")),
    SegmentPreset("tatuagem", "estúdio de tatuagem", "Beleza & Bem-estar", ("tatuador", "tattoo studio")),

    SegmentPreset("restaurante", "restaurante", "Alimentação & Hospitalidade"),
    SegmentPreset("pizzaria", "pizzaria", "Alimentação & Hospitalidade"),
    SegmentPreset("cafeteria", "cafeteria", "Alimentação & Hospitalidade", ("cafe", "café")),
    SegmentPreset("confeitaria", "confeitaria", "Alimentação & Hospitalidade", ("doceria", "bolos")),

    SegmentPreset("contabilidade", "escritório de contabilidade", "Serviços Profissionais", ("contador", "contabilidade")),
    SegmentPreset("arquitetura", "escritório de arquitetura", "Serviços Profissionais", ("arquiteto", "arquitetura")),
    SegmentPreset("fotografia", "fotógrafo", "Serviços Profissionais", ("fotografo", "fotografia")),
    SegmentPreset("imobiliaria", "imobiliária", "Serviços Profissionais", ("imobiliaria", "corretora de imoveis", "corretora de imóveis")),
    SegmentPreset("eventos", "empresa de eventos", "Serviços Profissionais", ("buffet de eventos", "decoracao de festas", "decoração de festas")),

    SegmentPreset("pet-shop", "pet shop", "Comércio & Serviços Locais", ("petshop",)),
    SegmentPreset("assistencia-celular", "assistência técnica de celular", "Comércio & Serviços Locais", ("conserto de celular", "assistencia celular")),
    SegmentPreset("informatica", "assistência técnica de informática", "Comércio & Serviços Locais", ("manutencao de computador", "manutenção de computador")),
    SegmentPreset("grafica", "gráfica", "Comércio & Serviços Locais", ("grafica", "comunicacao visual", "comunicação visual")),
)


_LOOKUP: dict[str, SegmentPreset] = {}
for preset in SEGMENTS:
    for value in (preset.slug, preset.label, *preset.aliases):
        _LOOKUP[_norm(value)] = preset


def resolve_segment(value: str) -> SegmentPreset | None:
    return _LOOKUP.get(_norm(value))


def grouped_segments() -> dict[str, list[SegmentPreset]]:
    grouped: dict[str, list[SegmentPreset]] = {}
    for preset in SEGMENTS:
        grouped.setdefault(preset.category, []).append(preset)
    return grouped
