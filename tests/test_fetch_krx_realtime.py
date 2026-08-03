import os
import unittest
from datetime import datetime, timezone
from unittest.mock import mock_open, patch

from scripts import fetch_krx_realtime


class FetchKrxRealtimeTest(unittest.TestCase):
    @staticmethod
    def _krx_response():
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "basDt": "20260731",
                                "itmsNm": "금 99.99_1Kg",
                                "clpr": "187460",
                                "vs": "1470",
                                "fltRt": "0.79",
                            }
                        ]
                    }
                },
            }
        }
        return response

    def test_missing_api_key_fails_before_writing(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("builtins.open", mock_open()) as output_file,
        ):
            with self.assertRaisesRegex(fetch_krx_realtime.UpstreamDataError, "KOREADATA_API_KEY"):
                fetch_krx_realtime.run()

        output_file.assert_not_called()

    def test_result_marks_cross_timestamp_premium_unavailable(self):
        krx_data = {
            "name": "금 99.99_1Kg",
            "price": 187460.0,
            "change": 100.0,
            "changePercent": 0.05,
            "high": 188000.0,
            "low": 186000.0,
            "volume": 100,
            "date": "20260731",
        }
        now = datetime(2026, 8, 3, 13, 0, tzinfo=timezone.utc)

        result = fetch_krx_realtime.build_result(
            now,
            krx_data,
            international_price=4066.1,
            international_as_of="2026-08-03T13:00:00+00:00",
            exchange_rate=1443.61,
            exchange_rate_date="2026-07-31",
        )

        self.assertIsNone(result["premium"])
        self.assertFalse(result["premiumAvailable"])
        self.assertEqual(result["international"]["asOf"], "2026-08-03T13:00:00+00:00")
        self.assertEqual(result["exchangeRateDate"], "2026-07-31")
        self.assertEqual(result["korean"]["source"], "KRX")

    def test_exchange_rate_failure_has_no_fixed_fallback(self):
        with patch.object(
            fetch_krx_realtime.requests,
            "get",
            side_effect=RuntimeError("timeout"),
        ):
            with self.assertRaises(fetch_krx_realtime.UpstreamDataError):
                fetch_krx_realtime.get_exchange_rate()

    def test_krx_request_failure_does_not_echo_api_key(self):
        with patch.object(
            fetch_krx_realtime.requests,
            "get",
            side_effect=RuntimeError("request URL contained secret-value"),
        ):
            with self.assertRaises(fetch_krx_realtime.UpstreamDataError) as raised:
                fetch_krx_realtime.get_krx_gold_price(
                    "secret-value",
                    datetime(2026, 8, 3, tzinfo=timezone.utc),
                )

        self.assertNotIn("secret-value", str(raised.exception))

    def test_krx_request_retries_transient_connect_timeout(self):
        with (
            patch.object(
                fetch_krx_realtime.requests,
                "get",
                side_effect=[
                    fetch_krx_realtime.requests.ConnectTimeout("timeout"),
                    self._krx_response(),
                ],
            ) as request,
            patch.object(fetch_krx_realtime.time, "sleep") as sleep,
        ):
            result = fetch_krx_realtime.get_krx_gold_price(
                "test-key",
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )

        self.assertEqual(result["date"], "20260731")
        self.assertEqual(result["price"], 187460.0)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_cli_main_returns_nonzero_for_upstream_failure(self):
        with patch.object(
            fetch_krx_realtime,
            "run",
            side_effect=fetch_krx_realtime.UpstreamDataError("timeout"),
        ):
            self.assertEqual(fetch_krx_realtime.main(), 1)


if __name__ == "__main__":
    unittest.main()
