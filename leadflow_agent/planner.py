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


def build_plan(goal: SearchGoal, llm: LLMProvider | None, *, max_queries: int = 6) -> QueryPlan:
    if llm is None:
        return BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)
    try:
        return llm.plan_queries(goal, max_queries=max_queries)
    except Exception as exc:
        fallback = BasicQueryPlanner().plan_queries(goal, max_queries=max_queries)
        fallback.rationale = f"LLM planner falhou ({exc}); usando fallback determinístico."
        fallback.generated_by = "basic:fallback"
        return fallback
