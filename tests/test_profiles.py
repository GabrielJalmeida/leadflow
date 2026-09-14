import unittest

from leadflow_agent.models import OpportunityType, WebsiteStatus
from leadflow_agent.profiles import get_profile
from leadflow_agent.segments import resolve_segment


class ProfileTests(unittest.TestCase):
    def test_segment_alias_resolves_to_preset(self):
        preset = resolve_segment("móveis planejados")
        self.assertIsNotNone(preset)
        self.assertEqual(preset.slug, "marcenaria")

    def test_unknown_segment_remains_custom(self):
        self.assertIsNone(resolve_segment("vendedor de milho"))

    def test_new_site_profile(self):
        spec = get_profile("new-site").filters()
        self.assertEqual(spec.website_states, {WebsiteStatus.NOT_FOUND})
        self.assertEqual(spec.readiness.value, "ready")

    def test_website_sales_profile_contains_main_types(self):
        spec = get_profile("website-sales").filters()
        self.assertIn(OpportunityType.NEW_SITE, spec.opportunity_types)
        self.assertIn(OpportunityType.REDESIGN, spec.opportunity_types)


if __name__ == "__main__":
    unittest.main()
