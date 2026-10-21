import importlib.util
from pathlib import Path
import unittest

TARGET = Path(__file__).resolve().parents[1] / "order_error_review_colab.py"


class ErrorReviewTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TARGET.exists(), "The separate error-review stage is not implemented yet.")
        spec = importlib.util.spec_from_file_location("error_review", TARGET)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_whole_order_group_is_preserved_and_matching_line_is_located(self):
        lines = ["Sending order 123", "Connection timed out", "Retry succeeded"]
        result = self.module.review_lines(lines, [{"match":"timed out", "severity":"Warning", "message":"Request timeout"}])
        self.assertEqual(result["lines"], lines)
        self.assertEqual(result["highest_severity"], "Warning")
        self.assertEqual(result["findings"][0]["line_number"], 2)
        self.assertTrue(result["has_alert"])

    def test_specific_ignore_suppresses_broad_match_but_not_other_error(self):
        rules = [
            {"match":"ERROR", "severity":"Critical", "message":"General error"},
            {"match":"ERROR CODE 123 expected", "severity":"Ignore", "message":"Known harmless message"},
            {"match":"connection lost", "severity":"Warning", "message":"Connection problem"}
        ]
        result = self.module.review_lines(["ERROR CODE 123 expected; connection lost"], rules)
        self.assertEqual(result["highest_severity"], "Warning")
        self.assertEqual(len([f for f in result["findings"] if f["alert"]]), 1)

    def test_group_uses_highest_severity_and_keeps_both_findings(self):
        rules = [
            {"match":"retry", "severity":"Warning", "message":"Retry"},
            {"match":"stopped", "severity":"Critical", "message":"Stopped"}
        ]
        result = self.module.review_lines(["retry", "stopped"], rules)
        self.assertEqual(result["highest_severity"], "Critical")
        self.assertEqual(len(result["findings"]), 2)

    def test_ignored_errors_are_recorded_without_alert(self):
        result = self.module.review_lines(["EXPECTED TIMEOUT"], [{"match":"expected timeout", "severity":"Ignore", "message":"Ignore this"}])
        self.assertFalse(result["has_alert"])
        self.assertEqual(result["highest_severity"], "None")
        self.assertEqual(len(result["findings"]), 1)

    def test_unassigned_error_is_not_attached_to_an_order(self):
        runs = [{"run_number":7, "run_status":"complete", "orders":[{"status":"complete", "lines":["normal order"]}], "unassigned_lines":["timeout outside order"]}]
        result = self.module.review_runs(runs, [{"match":"timeout", "severity":"Warning", "message":"Timeout"}], "INTERBANK")
        self.assertFalse(result[0]["orders"][0]["has_alert"])
        self.assertTrue(result[0]["unassigned_review"]["has_alert"])
        self.assertEqual(result[0]["run_number"], 7)

    def test_does_not_claim_success_after_retry_or_change_group_status(self):
        runs = [{"run_number":1, "run_status":"complete", "orders":[{"status":"incomplete", "lines":["timeout", "retry succeeded"]}], "unassigned_lines":[]}]
        result = self.module.review_runs(runs, [{"match":"timeout", "severity":"Warning", "message":"Timeout"}], "Cam")
        self.assertEqual(result[0]["orders"][0]["status"], "incomplete")
        self.assertEqual(result[0]["orders"][0]["outcome"], "not_assessed")
        self.assertNotIn("has_alert", runs[0]["orders"][0])


if __name__ == "__main__":
    unittest.main()
