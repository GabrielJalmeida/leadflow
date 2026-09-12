from __future__ import annotations

from .models import QueryPlan, SearchGoal
from .providers.base import LLMProvider


class BasicQueryPlanner:
    name = "basic"

    def plan_queries(self, goal: SearchGoal, *, max_queries: int = 6) -> QueryPlan:
        base = goal.segment.strip()
        folded = base.casefold()
        if "marcenar" in folded:
            candidates = [
                base,
                "móveis planejados",
                "marceneiro",
                "fabricação de móveis sob medida",
                "marcenaria artesanal",
                "projetos de marcenaria",
            ]
        else:
            # Generic fallback stays deterministic and useful without pretending
            # to know domain-specific synonyms for every possible segment.
            candidates = [
                base,
                f"{base} orçamento",
                f"{base} serviços",
                f"{base} atendimento",
            ]
        clean: list[str] = []
        for query in candidates:
            query = " ".join(query.split())
            if query and query.casefold() not in {q.casefold() for q in clean}:
                clean.append(query)
        return QueryPlan(
            queries=clean[: max(1, max_queries)],
            rationale="Fallback determinístico sem LLM. Use uma chave de IA para expansão semântica de consultas.",
            generated_by="basic",
        )


def _expand_plan_to_budget(plan: QueryPlan, goal: SearchGoal, *, max_queries: int) -> QueryPlan:
    """Expande planos curtos com ângulos determinísticos relevantes."""
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

def build_plan(goal: SearchGoal, llm: LLMProvider | None, *, max_queries: int = 6) -> QueryPlan:
    if llm is None:
        plan = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)
        return _expand_plan_to_budget(plan, goal, max_queries=max_queries)
    try:
        plan = llm.plan_queries(goal, max_queries=max_queries)
        return _expand_plan_to_budget(plan, goal, max_queries=max_queries)
    except Exception as exc:
        fallback = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)
        fallback.rationale = f"LLM planner falhou ({exc}); usando fallback determinístico."
        fallback.generated_by = "basic:fallback"
        return _expand_plan_to_budget(fallback, goal, max_queries=max_queries)
