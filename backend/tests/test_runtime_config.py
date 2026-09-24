import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import runtime_config


class RuntimeConfigTests(unittest.TestCase):
    @patch("runtime_config.boto3.client")
    def test_batches_ssm_requests_at_ten_names(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        def response(*, Names, WithDecryption):
            self.assertTrue(WithDecryption)
            return {
                "Parameters": [
                    {
                        "Name": name,
                        "Value": "06:15" if name.endswith("/DailyNotificationDefaultTime") else "12" if name.endswith("/SearchMaxFanout") else "24" if name.endswith("/SearchMaxSortPages") else "1000" if name.rsplit("/", 1)[-1] in {
                            "SearchCacheTtlSeconds",
                            "SearchDefaultLookbackDays",
                            "SearchMaxLookbackDays",
                            "SamPageSize",
                            "SamRequestTimeoutSeconds",
                            "HistoryRetentionDays",
                            "DailyFeedPageSize",
                            "DailyFeedRetentionDays",
                            "NotificationRunRetentionDays",
                        } else "value",
                    }
                    for name in Names
                ]
            }

        client.get_parameters.side_effect = response
        runtime_config._cached = None
        runtime_config._cached_at = 0
        with patch.dict(os.environ, {"CONFIG_PREFIX": "/govvue-light/dev"}):
            loaded = runtime_config.get_runtime_config()
        self.assertEqual(loaded.daily_feed_page_size, 1000)
        self.assertEqual(loaded.daily_notification_default_time, "06:15")
        self.assertEqual(client.get_parameters.call_count, 2)
        self.assertTrue(all(len(call.kwargs["Names"]) <= 10 for call in client.get_parameters.call_args_list))


if __name__ == "__main__":
    unittest.main()
