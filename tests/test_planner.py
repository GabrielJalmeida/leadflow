from __future__ import annotations

import unittest

from leadflow_agent.models import SearchGoal
from leadflow_agent.planner import BasicQueryPlanner


class BasicPlannerTests(unittest.TestCase):
    def test_marcenaria_fallback_uses_useful_synonyms(self):
        plan = BasicQueryPlanner().plan_queries(
            SearchGoal(segment="marcenaria", city="Praia Grande", state="SP"),
            max_queries=6,
        )
        self.assertEqual(plan.queries[0], "marcenaria")
        self.assertIn("móveis planejados", plan.queries)
        self.assertIn("marceneiro", plan.queries)
        self.assertNotIn("marcenaria empresa", plan.queries)
        self.assertNotIn("marcenaria profissional", plan.queries)


if __name__ == "__main__":
    unittest.main()
