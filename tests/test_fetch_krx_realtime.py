import json
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

    def test_exchange_rate_retries_transient_timeout(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "rates": {"KRW": 1427.11},
            "date": "2026-08-04",
        }

        with (
            patch.object(
                fetch_krx_realtime.requests,
                "get",
                side_effect=[
                    fetch_krx_realtime.requests.ReadTimeout("timeout"),
                    response,
                ],
            ) as request,
            patch.object(fetch_krx_realtime.time, "sleep") as sleep,
        ):
            rate, rate_date = fetch_krx_realtime.get_exchange_rate()

        self.assertEqual(rate, 1427.11)
        self.assertEqual(rate_date, "2026-08-04")
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_exchange_rate_retries_http_503(self):
        unavailable = unittest.mock.Mock()
        unavailable.status_code = 503
        unavailable.raise_for_status.side_effect = fetch_krx_realtime.requests.HTTPError(
            "service unavailable",
            response=unavailable,
        )
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "rates": {"KRW": 1427.11},
            "date": "2026-08-04",
        }

        with (
            patch.object(
                fetch_krx_realtime.requests,
                "get",
                side_effect=[unavailable, response],
            ) as request,
            patch.object(fetch_krx_realtime.time, "sleep") as sleep,
        ):
            rate, _ = fetch_krx_realtime.get_exchange_rate()

        self.assertEqual(rate, 1427.11)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_international_gold_price_retries_transient_timeout(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "price": 4164.0,
            "updatedAt": "2026-08-05T06:01:13Z",
        }
        now = datetime(2026, 8, 5, 6, 1, tzinfo=timezone.utc)

        with (
            patch.object(
                fetch_krx_realtime.requests,
                "get",
                side_effect=[
                    fetch_krx_realtime.requests.ConnectTimeout("timeout"),
                    response,
                ],
            ) as request,
            patch.object(fetch_krx_realtime.time, "sleep") as sleep,
        ):
            price, as_of = fetch_krx_realtime.get_international_gold_price(now)

        self.assertEqual(price, 4164.0)
        self.assertEqual(as_of, "2026-08-05T06:01:13Z")
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    @staticmethod
    def _cached_result():
        return {
            "lastUpdated": "2026-08-05T15:01:27.068685+09:00",
            "dataDate": "20260804",
            "korean": {
                "price": 186720.0,
                "change": 290.0,
                "changePercent": 0.16,
                "source": "KRX",
            },
            "international": {
                "priceUsd": 4164.0,
                "priceKrw": 191055.22,
                "asOf": "2026-08-05T06:01:13Z",
            },
            "exchangeRate": 1427.11,
            "exchangeRateDate": "2026-08-04",
            "premium": None,
            "premiumAvailable": False,
        }

    def test_run_uses_recent_cached_krx_data_after_upstream_failure(self):
        now = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)

        with (
            patch.object(
                fetch_krx_realtime,
                "get_krx_gold_price",
                side_effect=fetch_krx_realtime.TransientUpstreamDataError(
                    "KRX timeout"
                ),
            ),
            patch.object(
                fetch_krx_realtime,
                "get_international_gold_price",
                return_value=(4170.0, "2026-08-05T07:00:00Z"),
            ),
            patch.object(
                fetch_krx_realtime,
                "get_exchange_rate",
                return_value=(1428.0, "2026-08-05"),
            ),
            patch("builtins.open", mock_open(read_data=json.dumps(self._cached_result()))),
            patch.object(fetch_krx_realtime.json, "dump") as dump,
        ):
            result = fetch_krx_realtime.run(now_kst=now, api_key="test-key")

        self.assertEqual(result, 0)
        saved = dump.call_args.args[0]
        self.assertEqual(saved["dataDate"], "20260804")
        self.assertEqual(saved["korean"]["price"], 186720.0)
        self.assertEqual(saved["international"]["priceUsd"], 4170.0)

    def test_run_uses_recent_cached_exchange_rate_after_upstream_failure(self):
        now = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)
        krx_data = {
            "name": "금 99.99_1Kg",
            "price": 186720.0,
            "change": 290.0,
            "changePercent": 0.16,
            "high": 187000.0,
            "low": 185000.0,
            "volume": 100,
            "date": "20260804",
        }

        with (
            patch.object(fetch_krx_realtime, "get_krx_gold_price", return_value=krx_data),
            patch.object(
                fetch_krx_realtime,
                "get_international_gold_price",
                return_value=(4170.0, "2026-08-05T07:00:00Z"),
            ),
            patch.object(
                fetch_krx_realtime,
                "get_exchange_rate",
                side_effect=fetch_krx_realtime.TransientUpstreamDataError(
                    "FX timeout"
                ),
            ),
            patch("builtins.open", mock_open(read_data=json.dumps(self._cached_result()))),
            patch.object(fetch_krx_realtime.json, "dump") as dump,
        ):
            result = fetch_krx_realtime.run(now_kst=now, api_key="test-key")

        self.assertEqual(result, 0)
        saved = dump.call_args.args[0]
        self.assertEqual(saved["exchangeRate"], 1427.11)
        self.assertEqual(saved["exchangeRateDate"], "2026-08-04")

    def test_run_rejects_expired_cached_krx_data(self):
        now = datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc)

        with (
            patch.object(
                fetch_krx_realtime,
                "get_krx_gold_price",
                side_effect=fetch_krx_realtime.TransientUpstreamDataError(
                    "KRX timeout"
                ),
            ),
            patch("builtins.open", mock_open(read_data=json.dumps(self._cached_result()))),
        ):
            with self.assertRaisesRegex(
                fetch_krx_realtime.UpstreamDataError,
                "Cached KRX data is too old",
            ):
                fetch_krx_realtime.run(now_kst=now, api_key="test-key")

    def test_run_does_not_mask_non_transient_krx_failure(self):
        now = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)

        with (
            patch.object(
                fetch_krx_realtime,
                "get_krx_gold_price",
                side_effect=fetch_krx_realtime.UpstreamDataError("invalid KRX payload"),
            ),
            patch.object(fetch_krx_realtime, "_cached_krx_data") as cached_krx,
        ):
            with self.assertRaisesRegex(
                fetch_krx_realtime.UpstreamDataError,
                "invalid KRX payload",
            ):
                fetch_krx_realtime.run(now_kst=now, api_key="test-key")

        cached_krx.assert_not_called()

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

    def test_krx_request_uses_recent_range_and_selects_latest_date(self):
        response = self._krx_response()
        response.json.return_value["response"]["body"]["items"]["item"] = [
            {
                "basDt": "20260730",
                "itmsNm": "금 99.99_1Kg",
                "clpr": "185990",
                "vs": "-100",
                "fltRt": "-0.05",
            },
            {
                "basDt": "20260731",
                "itmsNm": "금 99.99_1Kg",
                "clpr": "187460",
                "vs": "1470",
                "fltRt": "0.79",
            },
        ]

        with patch.object(
            fetch_krx_realtime.requests,
            "get",
            return_value=response,
        ) as request:
            result = fetch_krx_realtime.get_krx_gold_price(
                "test-key",
                datetime(2026, 8, 3, tzinfo=timezone.utc),
            )

        params = request.call_args.kwargs["params"]
        self.assertEqual(params["beginBasDt"], "20260725")
        self.assertEqual(params["endBasDt"], "20260803")
        self.assertNotIn("basDt", params)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result["date"], "20260731")
        self.assertEqual(result["price"], 187460.0)

    def test_cli_main_returns_nonzero_for_upstream_failure(self):
        with patch.object(
            fetch_krx_realtime,
            "run",
            side_effect=fetch_krx_realtime.UpstreamDataError("timeout"),
        ):
            self.assertEqual(fetch_krx_realtime.main(), 1)


if __name__ == "__main__":
    unittest.main()
