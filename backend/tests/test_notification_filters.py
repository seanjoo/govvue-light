import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from notification_filters import matches, sanitize_criteria


class NotificationFiltersTests(unittest.TestCase):
    def opportunity(self, **overrides):
        value = {
            "active": True,
            "title": "Cybersecurity support services",
            "notice_id": "abc123",
            "solicitation_number": "SOL-42",
            "type": "Combined Synopsis/Solicitation",
            "type_code": "k",
            "naics_code": "541512",
            "classification_code": "DA01",
            "set_aside": "Small Business Set-Aside",
            "set_aside_code": "SBA",
            "organization_name": "Department of Example",
            "agency_path": "EXAMPLE.SUBTIER.OFFICE",
            "organization_code": "123",
            "response_deadline": "2026-10-15T12:00:00-04:00",
            "place_of_performance": {"state": "VA", "zip": "22102"},
        }
        value.update(overrides)
        return value

    def test_matches_combined_filters(self):
        criteria = sanitize_criteria(
            {
                "title": "cybersecurity",
                "ptype": "k",
                "naics_code": "541512",
                "state": "va",
                "set_aside": "SBA",
                "response_deadline_to": "2026-10-31",
                "posted_from": "2026-09-19",
                "posted_to": "2026-09-20",
                "posted_within": "30",
            }
        )
        self.assertNotIn("posted_from", criteria)
        self.assertNotIn("posted_to", criteria)
        self.assertNotIn("posted_within", criteria)
        self.assertTrue(matches(self.opportunity(), criteria))

    def test_rejects_inactive_or_nonmatching(self):
        self.assertFalse(matches(self.opportunity(active=False), {}))
        self.assertFalse(matches(self.opportunity(), {"state": "MD"}))

    def test_invalid_deadline(self):
        with self.assertRaises(ValueError):
            sanitize_criteria({"response_deadline_from": "not-a-date"})

    def test_multiple_values_use_or_within_each_filter(self):
        self.assertTrue(
            matches(
                self.opportunity(),
                {
                    "ptype": "o,k,p",
                    "set_aside": "8A,SBA",
                    "state": "MD,VA",
                    "naics_code": "541511,541512",
                },
            )
        )

    def test_multiple_values_still_require_each_filter(self):
        self.assertFalse(
            matches(
                self.opportunity(),
                {"ptype": "o,k", "state": "MD,DC"},
            )
        )

    def test_open_deadlines_only_rejects_past_due_opportunities(self):
        criteria = sanitize_criteria({"open_deadlines_only": "true"})
        past = (date.today() - timedelta(days=1)).isoformat()
        today = date.today().isoformat()
        self.assertFalse(matches(self.opportunity(response_deadline=past), criteria))
        self.assertTrue(matches(self.opportunity(response_deadline=today), criteria))

    def test_open_deadlines_only_requires_a_known_deadline(self):
        criteria = sanitize_criteria({"open_deadlines_only": "true"})
        self.assertFalse(matches(self.opportunity(response_deadline=""), criteria))


if __name__ == "__main__":
    unittest.main()
