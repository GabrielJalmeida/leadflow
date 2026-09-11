from __future__ import annotations

import socket
import unittest

from leadflow_agent.models import Lead, WebsiteAudit, WebsiteStatus
from leadflow_agent.services.website_auditor import (
    FetchResult,
    UnsafeWebsiteUrl,
    WebsiteAuditor,
    validate_public_http_url,
)


class FakeFetcher:
    def __init__(self, result: FetchResult):
        self.result = result
        self.calls = 0

    def fetch(self, url: str, *, timeout: float = 8.0) -> FetchResult:
        self.calls += 1
        return self.result


def public_resolver(host, port, *, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, type, 6, "", ("93.184.216.34", port))]


def private_resolver(host, port, *, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, type, 6, "", ("192.168.1.10", port))]


class WebsiteAuditorTests(unittest.TestCase):
    def test_full_signal_site_scores_100(self):
        html = b'''<!doctype html><html><head><title>Empresa X</title>
        <meta name="description" content="Moveis planejados">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        </head><body><a href="https://wa.me/5513999999999">WhatsApp</a><form></form></body></html>'''
        fetcher = FakeFetcher(FetchResult(
            requested_url="https://empresa.example",
            final_url="https://empresa.example/",
            status_code=200,
            response_time_ms=120,
            redirect_count=0,
            content_type="text/html; charset=utf-8",
            body=html,
        ))
        lead = Lead(name="Empresa X", website="https://empresa.example")
        outcome = WebsiteAuditor(fetcher).audit(lead)
        self.assertFalse(outcome.reused)
        self.assertEqual(outcome.audit.technical_score, 100)
        self.assertTrue(outcome.audit.has_whatsapp)
        self.assertTrue(outcome.audit.has_viewport)
        self.assertEqual(lead.website_status, WebsiteStatus.PRESENT)

    def test_missing_static_signals_are_reported(self):
        fetcher = FakeFetcher(FetchResult(
            requested_url="http://empresa.example",
            final_url="http://empresa.example",
            status_code=200,
            response_time_ms=80,
            redirect_count=0,
            content_type="text/html",
            body=b"<html><body>ola</body></html>",
        ))
        lead = Lead(name="Empresa X", website="http://empresa.example")
        audit = WebsiteAuditor(fetcher).audit(lead).audit
        self.assertLess(audit.technical_score, 100)
        self.assertIn("site sem HTTPS", audit.findings)
        self.assertIn("meta viewport não detectada", audit.findings)

    def test_network_failure_marks_site_unreachable(self):
        fetcher = FakeFetcher(FetchResult(
            requested_url="https://empresa.example",
            final_url="https://empresa.example",
            status_code=None,
            response_time_ms=2000,
            redirect_count=0,
            content_type="",
            body=b"",
            error="timed out",
        ))
        lead = Lead(name="Empresa X", website="https://empresa.example")
        audit = WebsiteAuditor(fetcher).audit(lead).audit
        self.assertFalse(audit.reachable)
        self.assertEqual(lead.website_status, WebsiteStatus.UNREACHABLE)

    def test_safety_block_does_not_claim_unreachable(self):
        fetcher = FakeFetcher(FetchResult(
            requested_url="http://127.0.0.1",
            final_url="http://127.0.0.1",
            status_code=None,
            response_time_ms=1,
            redirect_count=0,
            content_type="",
            body=b"",
            error="non-public IP blocked",
            blocked=True,
        ))
        lead = Lead(name="Empresa X", website="http://127.0.0.1")
        audit = WebsiteAuditor(fetcher).audit(lead).audit
        self.assertTrue(audit.blocked)
        self.assertEqual(lead.website_status, WebsiteStatus.PRESENT)

    def test_recent_audit_is_reused_without_fetch(self):
        existing = WebsiteAudit(
            requested_url="https://empresa.example",
            final_url="https://empresa.example",
            reachable=True,
            status_code=200,
            technical_score=90,
        )
        fetcher = FakeFetcher(FetchResult(
            requested_url="https://empresa.example",
            final_url="https://empresa.example",
            status_code=500,
            response_time_ms=1,
            redirect_count=0,
            content_type="text/html",
            body=b"",
        ))
        lead = Lead(name="Empresa X", website="https://empresa.example", website_audit=existing)
        outcome = WebsiteAuditor(fetcher).audit(lead, max_age_days=7)
        self.assertTrue(outcome.reused)
        self.assertEqual(fetcher.calls, 0)
        self.assertEqual(outcome.audit.technical_score, 90)

    def test_private_and_local_targets_are_blocked(self):
        for url in ("http://127.0.0.1", "http://localhost", "http://10.0.0.4"):
            with self.subTest(url=url):
                with self.assertRaises(UnsafeWebsiteUrl):
                    validate_public_http_url(url, resolver=public_resolver)
        with self.assertRaises(UnsafeWebsiteUrl):
            validate_public_http_url("https://example.com", resolver=private_resolver)

    def test_public_resolution_is_allowed(self):
        validate_public_http_url("https://example.com", resolver=public_resolver)


if __name__ == "__main__":
    unittest.main()
