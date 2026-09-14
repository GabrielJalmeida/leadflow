from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from leadflow_agent.benchmark import (
    automatic_metrics,
    build_review_rows,
    load_benchmark_cases,
    summarize_manual_review,
    validate_review_rows,
    write_review_csv,
)


class BenchmarkHarnessTests(unittest.TestCase):
    def test_official_cases_load_without_yaml_dependency(self) -> None:
        cases = load_benchmark_cases("benchmarks/cases.yaml")
        self.assertEqual(len(cases), 5)
        self.assertEqual(cases[0].id, "marcenaria-praia-grande-sp")
        self.assertEqual(cases[0].target, 10)

    def test_automatic_metrics_preserve_fulfillment_counters(self) -> None:
        metrics = automatic_metrics(
            {
                "goal": {"limit": 10},
                "leads": [{}, {}],
                "queries_executed": ["a", "b"],
                "discovery_unique_candidates": 17,
                "discovery_prequalified": 8,
                "duplicates_removed": 3,
                "usage_search_calls": 4,
                "usage_llm_calls": 2,
                "run_status": "partial",
                "run_stop_reason": "queries_exhausted",
            }
        )
        self.assertEqual(metrics["returned"], 2)
        self.assertEqual(metrics["fulfillment_at_n"], 0.2)
        self.assertEqual(metrics["unique_candidates"], 17)
        self.assertEqual(metrics["prequalified_candidates"], 8)
        self.assertFalse(metrics["quota_fulfilled"])


    def test_external_failures_invalidate_quality_gate_measurement(self) -> None:
        metrics = automatic_metrics(
            {
                "goal": {"limit": 10},
                "leads": [{} for _ in range(9)],
                "errors": ["query: Network error: Temporary failure in name resolution"],
                "website_audits_run": 4,
                "website_audit_errors": 4,
            }
        )
        self.assertFalse(metrics["quality_gate_measurement_valid"])
        self.assertEqual(metrics["external_failure_errors"], 1)
        self.assertEqual(metrics["website_audit_error_rate"], 1.0)
        self.assertTrue(metrics["validity_reasons"])

    def test_final_lead_audit_failures_invalidate_even_when_aggregate_rate_is_low(self) -> None:
        metrics = automatic_metrics(
            {
                "goal": {"limit": 10},
                "leads": [
                    {
                        "website_audit": {
                            "reachable": False,
                            "blocked": False,
                            "status_code": None,
                            "error": "hostname resolution failed",
                        }
                    },
                    {
                        "website_audit": {
                            "reachable": False,
                            "blocked": False,
                            "status_code": None,
                            "error": "timed out",
                        }
                    },
                ] + [{} for _ in range(8)],
                "website_audits_run": 10,
                "website_audit_errors": 2,
            }
        )
        self.assertEqual(metrics["website_audit_error_rate"], 0.2)
        self.assertEqual(metrics["final_website_audits"], 2)
        self.assertEqual(metrics["final_website_audit_errors"], 2)
        self.assertEqual(metrics["final_website_audit_error_rate"], 1.0)
        self.assertFalse(metrics["quality_gate_measurement_valid"])
        self.assertTrue(any("final-lead" in reason for reason in metrics["validity_reasons"]))

    def test_review_rows_contain_manual_columns_and_evidence_context(self) -> None:
        report = {
            "leads": [
                {
                    "name": "Marcenaria Exemplo",
                    "city": "Praia Grande",
                    "state": "SP",
                    "phone": "(13) 99999-0000",
                    "website": None,
                    "website_status": "not_found",
                    "socials": ["https://instagram.com/exemplo"],
                    "identity_status": "matched",
                    "identity_confidence": 0.99,
                    "confidence_score": 90,
                    "score": 80,
                    "provider_url": "https://example.com/source",
                    "evidence": [
                        {"url": "https://example.com/source"},
                        {"url": "https://instagram.com/exemplo"},
                    ],
                    "opportunity": {"type": "new_site"},
                }
            ]
        }
        rows = build_review_rows(report, benchmark_id="case-a", run_id=7)
        self.assertEqual(rows[0]["lead_name"], "Marcenaria Exemplo")
        self.assertEqual(rows[0]["website_status_predicted"], "not_found")
        self.assertEqual(rows[0]["opportunity_type_predicted"], "new_site")
        self.assertEqual(rows[0]["segment_match"], "")
        self.assertIn("instagram.com", rows[0]["source_urls"])

    def test_manual_summary_treats_duplicate_fail_as_duplicate_detected(self) -> None:
        row = {
            "canonical_name_correct": "PASS",
            "segment_match": "PASS",
            "city_match": "PASS",
            "state_match": "PASS",
            "real_business": "PASS",
            "identity_correct": "PASS",
            "phone_present": "PASS",
            "phone_plausible": "PASS",
            "instagram_correct": "PASS",
            "website_correctly_attributed": "PASS",
            "is_duplicate": "FAIL",
            "is_false_merge": "PASS",
            "contact_route_useful": "PASS",
            "evidence_sufficient": "PASS",
            "final_grade": "PASS",
        }
        summary = summarize_manual_review([row])
        self.assertEqual(summary["precision_at_n"], 1.0)
        self.assertEqual(summary["canonical_name_precision"], 1.0)
        self.assertEqual(summary["duplicate_rate"], 1.0)
        self.assertEqual(summary["false_merge_rate"], 0.0)
        self.assertEqual(summary["overall_pass_rate"], 1.0)

    def test_invalid_manual_value_is_reported(self) -> None:
        row = {field: "" for field in [
            "canonical_name_correct", "segment_match", "city_match", "state_match", "real_business",
            "identity_correct", "phone_present", "phone_plausible",
            "instagram_correct", "website_correctly_attributed", "is_duplicate",
            "is_false_merge", "contact_route_useful", "evidence_sufficient", "final_grade",
        ]}
        row["final_grade"] = "YES"
        errors = validate_review_rows([row])
        self.assertTrue(errors)

    def test_review_csv_round_trip_has_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            write_review_csv(path, [{"benchmark_id": "a", "rank": 1, "lead_name": "X"}])
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("benchmark_id", text.splitlines()[0])
            self.assertIn("lead_name", text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()

class BenchmarkFilterDiagnosticsTests(unittest.TestCase):
    def test_automatic_metrics_preserves_filter_rejection_reasons(self):
        report = {
            "goal": {"limit": 10},
            "leads": [],
            "filter_candidates_seen": 4,
            "filter_rejected": 4,
            "filter_rejection_reasons": {
                "opportunity=review_needed": 3,
                "no_contact_channel": 1,
            },
        }
        metrics = automatic_metrics(report)
        self.assertEqual(
            metrics["filter_rejection_reasons"],
            {"opportunity=review_needed": 3, "no_contact_channel": 1},
        )

