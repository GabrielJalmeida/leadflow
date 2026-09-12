from __future__ import annotations

import unittest

from leadflow_agent.gui import (
    GuiSearchConfig,
    build_contact_message,
    build_whatsapp_url,
    lead_row_values,
    resolve_contact_route,
    validate_gui_config,
)


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
        self.assertEqual(row[5], "WhatsApp?")
        self.assertEqual(row[6], "https://example.com")

    def test_mobile_phone_prefers_whatsapp_candidate(self):
        lead = {
            "name": "Example",
            "location": {"country": "Brazil"},
            "contact": {
                "phone": "(13) 99157-6100",
                "socials": ["https://www.instagram.com/example/"],
            },
            "opportunity": {"type": "new_site"},
        }
        route = resolve_contact_route(lead)
        self.assertEqual(route.channel, "whatsapp")
        self.assertEqual(route.whatsapp_number, "5513991576100")
        self.assertEqual(route.instagram_url, "https://www.instagram.com/example/")

    def test_fixed_line_prefers_instagram_when_available(self):
        lead = {
            "location": {"country": "Brazil"},
            "contact": {
                "phone": "(13) 3491-6447",
                "socials": [
                    "https://www.facebook.com/example",
                    "https://www.instagram.com/example/?hl=pt-br",
                ],
            },
        }
        route = resolve_contact_route(lead)
        self.assertEqual(route.channel, "instagram")
        self.assertEqual(route.label, "Instagram")
        self.assertEqual(route.whatsapp_number, "551334916447")

    def test_explicit_whatsapp_link_has_priority(self):
        lead = {
            "location": {"country": "Brazil"},
            "contact": {
                "phone": None,
                "socials": [
                    "https://www.instagram.com/example/",
                    "https://wa.me/5513999999999",
                ],
            },
        }
        route = resolve_contact_route(lead)
        self.assertEqual(route.channel, "whatsapp")
        self.assertEqual(route.whatsapp_source, "explicit")
        self.assertEqual(route.whatsapp_number, "5513999999999")

    def test_facebook_only_is_not_used_as_contact_channel(self):
        lead = {
            "location": {"country": "Brazil"},
            "contact": {"phone": None, "socials": ["https://www.facebook.com/example"]},
        }
        route = resolve_contact_route(lead)
        self.assertEqual(route.channel, "none")

    def test_whatsapp_url_contains_prefilled_message(self):
        url = build_whatsapp_url("5513999999999", "Olá, tudo bem?")
        self.assertTrue(url.startswith("https://wa.me/5513999999999?text="))
        self.assertIn("Ol%C3%A1%2C%20tudo%20bem%3F", url)

    def test_default_message_uses_lead_name(self):
        message = build_contact_message({
            "name": "Marcenaria Exemplo",
            "opportunity": {"type": "new_site"},
        })
        self.assertIn("Marcenaria Exemplo", message)
        self.assertIn("Posso te mostrar uma ideia", message)


if __name__ == "__main__":
    unittest.main()
