from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import search_interpreter


def config():
    return SimpleNamespace(
        ai_search_model_id="amazon.nova-lite-v1:0",
        ai_search_max_tokens=1000,
        search_default_lookback_days=30,
        search_max_lookback_days=365,
        search_max_fanout=12,
    )


class SearchInterpreterTests(unittest.TestCase):
    @patch("search_interpreter.boto3.client")
    def test_builds_and_validates_editable_existing_filters(self, client_factory):
        bedrock = MagicMock()
        client_factory.return_value = bedrock
        bedrock.converse.return_value = {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "used_company_profile": True,
                                    "interpretation": "Defense software support",
                                    "assumptions": ["Use a 30-day lookback"],
                                    "criteria": {
                                        "title": "software support",
                                        "ptype": ["o", "k"],
                                        "naics_code": ["541511", "541512"],
                                        "organization_name": ["Department of Defense", "Department of the Navy"],
                                        "unsupported": "ignored",
                                    },
                                }
                            )
                        }
                    ]
                }
            }
        }

        result = search_interpreter.interpret_search(
            "Find defense software opportunities that fit our company",
            "auto",
            {"overview": "Custom software developer"},
            config(),
        )

        self.assertTrue(result["used_company_profile"])
        self.assertEqual(result["criteria"]["ptype"], "o,k")
        self.assertEqual(result["criteria"]["posted_within"], "30")
        self.assertEqual(result["criteria"]["open_deadlines_only"], "true")
        self.assertEqual(
            result["criteria"]["organization_name"],
            "Department of Defense|Department of the Navy",
        )
        self.assertNotIn("unsupported", result["criteria"])

    def test_include_requires_a_populated_company_profile(self):
        with self.assertRaisesRegex(ValueError, "Add a company profile"):
            search_interpreter.interpret_search(
                "Find opportunities that fit our company", "include", {}, config()
            )

    def test_generated_plan_is_broadened_to_stay_within_fanout_limit(self):
        criteria, warnings = search_interpreter._criteria(
            {
                "naics_code": "541511,541512,541519,518210",
                "set_aside": "SBA,SBP,8A,8AN",
                "classification_code": "DA01,DA10,DB01",
            },
            config(),
        )
        self.assertLessEqual(search_interpreter._fanout_count(criteria), 12)
        self.assertNotIn("set_aside", criteria)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
