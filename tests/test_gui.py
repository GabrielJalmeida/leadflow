from __future__ import annotations

import unittest

from leadflow_agent.gui import GuiSearchConfig, lead_row_values, validate_gui_config


class GuiHelpersTests(unittest.TestCase):
    def test_default_gui_config_is_safe_and_bounded(self):
        config = validate_gui_config(GuiSearchConfig(segment="marcenaria", city="Praia Grande", state="SP"))
        self.assertEqual(config.limit, 10)
        self.assertEqual(config.profile, "website-sales")
        self.assertTrue(config.investigate)
        self.assertTrue(config.audit_websites)
        self.assertFalse(config.browser_audit)
        self.assertFalse(config.visual_audit)

    def test_custom_segment_is_allowed(self):
        config = validate_gui_config(GuiSearchConfig(segment="vendedor de milho", city="Praia Grande"))
        self.assertEqual(config.segment, "vendedor de milho")

    def test_gui_rejects_accidental_1000_leads(self):
        with self.assertRaises(ValueError):
            validate_gui_config(GuiSearchConfig(segment="marcenaria", city="Praia Grande", limit=1000))

    def test_gui_rejects_missing_city(self):
        with self.assertRaises(ValueError):
            validate_gui_config(GuiSearchConfig(segment="marcenaria", city="   "))

    def test_lead_row_values_uses_frontend_contract(self):
        lead = {
            "name": "Example Business",
            "contact": {"phone": "+55 13 99999-9999", "email": None, "socials": []},
            "website": {"url": "https://example.com", "status": "present"},
            "opportunity": {"score": 88, "type": "redesign", "actionable": True},
        }
        row = lead_row_values(lead)
        self.assertEqual(row[0], "88")
        self.assertEqual(row[1], "Example Business")
        self.assertEqual(row[2], "REDESIGN")
        self.assertEqual(row[3], "READY")
        self.assertEqual(row[4], "+55 13 99999-9999")
        self.assertEqual(row[5], "https://example.com")


if __name__ == "__main__":
    unittest.main()
