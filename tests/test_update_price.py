import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts import update_price


class UpdatePriceTest(unittest.TestCase):
    @staticmethod
    def _krx_response(date, price, page_size=1, total_count=2):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "numOfRows": page_size,
                    "totalCount": total_count,
                    "items": {
                        "item": [
                            {
                                "basDt": date,
                                "itmsNm": "금 99.99_1Kg",
                                "clpr": price,
                            }
                        ]
                    },
                },
            }
        }
        return response

    def test_krx_history_follows_response_pagination(self):
        responses = [
            self._krx_response("20260730", "185990"),
            self._krx_response("20260731", "187460"),
        ]

        with patch.object(update_price.requests, "get", side_effect=responses) as request:
            prices = update_price.get_korean_gold_prices(
                "test-key", "2026-07-30", "2026-08-03"
            )

        self.assertEqual(
            prices,
            {"2026-07-30": 185990.0, "2026-07-31": 187460.0},
        )
        self.assertEqual(request.call_count, 2)

    def test_valid_empty_krx_response_is_not_an_upstream_failure(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {"totalCount": 0, "items": {"item": []}},
            }
        }

        with patch.object(update_price.requests, "get", return_value=response):
            prices = update_price.get_korean_gold_prices(
                "test-key", "2026-08-01", "2026-08-03"
            )

        self.assertEqual(prices, {})

    def test_krx_history_failure_does_not_echo_api_key(self):
        with patch.object(
            update_price.requests,
            "get",
            side_effect=RuntimeError("request URL contained secret-value"),
        ):
            with self.assertRaises(update_price.UpstreamDataError) as raised:
                update_price.get_korean_gold_prices(
                    "secret-value", "2026-07-30", "2026-08-03"
                )

        self.assertNotIn("secret-value", str(raised.exception))

    def test_krx_history_retries_transient_connect_timeout(self):
        response = self._krx_response(
            "20260731",
            "187460",
            page_size=1,
            total_count=1,
        )

        with (
            patch.object(
                update_price.requests,
                "get",
                side_effect=[update_price.requests.ConnectTimeout("timeout"), response],
            ) as request,
            patch.object(update_price.time, "sleep") as sleep,
        ):
            prices = update_price.get_korean_gold_prices(
                "test-key", "2026-07-31", "2026-08-03"
            )

        self.assertEqual(prices, {"2026-07-31": 187460.0})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_valid_empty_exchange_rates_are_a_market_holiday(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "amount": 1.0,
            "base": "USD",
            "start_date": "2026-04-03",
            "end_date": "2026-04-03",
            "rates": {},
        }

        with patch.object(update_price.requests, "get", return_value=response):
            rates = update_price.fetch_exchange_rates("2026-04-03", "2026-04-03")

        self.assertEqual(rates, {})

    def test_run_backfills_every_missing_krx_date(self):
        history = {
            "lastUpdated": "2026-07-30",
            "data": [
                {
                    "date": "2026-07-01",
                    "koreanPrice": 180000,
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                },
                {
                    "date": "2026-07-30",
                    "koreanPrice": 185990,
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                },
            ],
        }
        krx_prices = {
            "2026-07-01": 180000.0,
            "2026-07-03": 181000.0,
            "2026-07-10": 182000.0,
            "2026-07-22": 183000.0,
            "2026-07-24": 184000.0,
            "2026-07-31": 187460.0,
        }
        lbma_prices = {
            "2026-07-03": 3300.0,
            "2026-07-10": 3400.0,
            "2026-07-22": 3450.0,
            "2026-07-24": 3475.0,
            "2026-07-31": 3500.0,
        }
        exchange_rates = {
            "2026-07-03": 1400.0,
            "2026-07-10": 1410.0,
            "2026-07-22": 1415.0,
            "2026-07-24": 1418.0,
            "2026-07-31": 1420.0,
        }

        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(update_price, "get_korean_gold_prices", return_value=krx_prices),
            patch.object(update_price, "fetch_lbma_prices", return_value=lbma_prices),
            patch.object(update_price, "fetch_exchange_rates", return_value=exchange_rates),
            patch.object(update_price, "save_history") as save_history,
        ):
            result = update_price.run(
                "daily",
                now_kst=datetime(2026, 8, 3, tzinfo=timezone.utc),
                koreadata_api_key="test-key",
            )

        self.assertEqual(result, 0)
        saved = save_history.call_args.args[0]
        self.assertEqual(
            [item["date"] for item in saved["data"]],
            [
                "2026-07-01",
                "2026-07-03",
                "2026-07-10",
                "2026-07-22",
                "2026-07-24",
                "2026-07-30",
                "2026-07-31",
            ],
        )
        self.assertEqual(saved["lastUpdated"], "2026-07-31")

    def test_realtime_mode_scans_from_latest_saved_date(self):
        history = {
            "lastUpdated": "2026-07-31",
            "data": [
                {"date": "2020-01-02", "koreanPrice": 60000.0},
                {"date": "2026-07-31", "koreanPrice": 187460.0},
            ],
        }

        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                return_value={},
            ) as get_prices,
            patch.object(update_price, "validate_history"),
        ):
            result = update_price.run(
                "realtime",
                now_kst=datetime(2026, 8, 3, tzinfo=timezone.utc),
                koreadata_api_key="test-key",
            )

        self.assertEqual(result, 0)
        get_prices.assert_called_once_with(
            "test-key", "2026-07-31", "2026-08-03"
        )

    def test_daily_mode_scans_only_rolling_window(self):
        history = {
            "lastUpdated": "2026-07-31",
            "data": [
                {"date": "2020-01-02", "koreanPrice": 60000.0},
                {"date": "2026-07-31", "koreanPrice": 187460.0},
            ],
        }

        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                return_value={},
            ) as get_prices,
            patch.object(update_price, "validate_history"),
        ):
            result = update_price.run(
                "daily",
                now_kst=datetime(2026, 8, 3, tzinfo=timezone.utc),
                koreadata_api_key="test-key",
            )

        self.assertEqual(result, 0)
        get_prices.assert_called_once_with(
            "test-key", "2026-05-05", "2026-08-03"
        )

    def test_run_does_not_call_other_upstreams_when_no_krx_date_is_missing(self):
        history = {
            "lastUpdated": "2026-07-31",
            "data": [
                {
                    "date": "2026-07-31",
                    "koreanPrice": 187460.0,
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                }
            ],
        }

        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                return_value={"2026-07-31": 187460.0},
            ),
            patch.object(update_price, "fetch_lbma_prices") as fetch_lbma,
            patch.object(update_price, "fetch_exchange_rates") as fetch_rates,
            patch.object(update_price, "save_history") as save_history,
        ):
            result = update_price.run(
                "daily",
                now_kst=datetime(2026, 8, 3, tzinfo=timezone.utc),
                koreadata_api_key="test-key",
            )

        self.assertEqual(result, 0)
        fetch_lbma.assert_not_called()
        fetch_rates.assert_not_called()
        save_history.assert_not_called()

    def test_build_entries_marks_cross_market_holiday_premium_unavailable(self):
        entries = update_price.build_entries(
            {"2026-04-03": 180000.0},
            {},
            {},
        )

        self.assertEqual(
            entries,
            [
                {
                    "date": "2026-04-03",
                    "koreanPrice": 180000.0,
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                }
            ],
        )

    def test_run_saves_krx_date_when_lbma_market_was_closed(self):
        history = {
            "lastUpdated": "2026-04-02",
            "data": [
                {
                    "date": "2026-04-02",
                    "koreanPrice": 179000.0,
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                }
            ],
        }

        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                return_value={"2026-04-02": 179000.0, "2026-04-03": 180000.0},
            ),
            patch.object(update_price, "fetch_lbma_prices", return_value={"2026-04-02": 3300.0}),
            patch.object(
                update_price,
                "fetch_exchange_rates",
                return_value={},
            ),
            patch.object(update_price, "save_history") as save_history,
        ):
            result = update_price.run(
                "daily",
                now_kst=datetime(2026, 4, 6, tzinfo=timezone.utc),
                koreadata_api_key="test-key",
            )

        self.assertEqual(result, 0)
        saved_entry = save_history.call_args.args[0]["data"][-1]
        self.assertEqual(saved_entry["date"], "2026-04-03")
        self.assertIsNone(saved_entry["premium"])
        self.assertFalse(saved_entry["premiumAvailable"])

    def test_build_entries_marks_same_date_comparison_available(self):
        entry = update_price.build_entries(
            {"2026-07-31": 187460.0},
            {"2026-07-31": 3500.0},
            {"2026-07-31": 1420.0},
        )[0]

        self.assertTrue(entry["premiumAvailable"])
        self.assertIsInstance(entry["premium"], float)

    def test_validate_history_rejects_duplicate_dates(self):
        history = {
            "lastUpdated": "2026-07-31",
            "data": [
                {"date": "2026-07-31", "koreanPrice": 187460.0},
                {"date": "2026-07-31", "koreanPrice": 187460.0},
            ],
        }

        with self.assertRaisesRegex(update_price.UpstreamDataError, "Duplicate"):
            update_price.validate_history(history)

    def test_validate_history_rejects_inconsistent_premium(self):
        history = {
            "lastUpdated": "2026-07-31",
            "data": [
                {
                    "date": "2026-07-31",
                    "koreanPrice": 187460.0,
                    "internationalPrice": 4026.6,
                    "internationalPriceKrw": 186887.01,
                    "exchangeRate": 1443.61,
                    "premium": 99.0,
                    "premiumAvailable": True,
                }
            ],
        }

        with self.assertRaisesRegex(update_price.UpstreamDataError, "premium"):
            update_price.validate_history(history)

    def test_upstream_failure_never_saves_history(self):
        with (
            patch.object(update_price, "load_history", return_value={"lastUpdated": "", "data": []}),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                side_effect=update_price.UpstreamDataError("KRX unavailable"),
            ),
            patch.object(update_price, "save_history") as save_history,
        ):
            with self.assertRaisesRegex(update_price.UpstreamDataError, "KRX unavailable"):
                update_price.run(
                    "daily",
                    now_kst=datetime(2026, 8, 3, tzinfo=timezone.utc),
                    koreadata_api_key="test-key",
                )

        save_history.assert_not_called()

    def test_comparison_api_failure_never_saves_partial_history(self):
        history = {"lastUpdated": "2026-04-02", "data": [{"date": "2026-04-02"}]}
        with (
            patch.object(update_price, "load_history", return_value=history),
            patch.object(
                update_price,
                "get_korean_gold_prices",
                return_value={"2026-04-02": 179000.0, "2026-04-03": 180000.0},
            ),
            patch.object(update_price, "fetch_lbma_prices", return_value={}),
            patch.object(
                update_price,
                "fetch_exchange_rates",
                side_effect=update_price.UpstreamDataError("Frankfurter timeout"),
            ),
            patch.object(update_price, "save_history") as save_history,
        ):
            with self.assertRaisesRegex(update_price.UpstreamDataError, "Frankfurter timeout"):
                update_price.run(
                    "daily",
                    now_kst=datetime(2026, 4, 6, tzinfo=timezone.utc),
                    koreadata_api_key="test-key",
                )

        save_history.assert_not_called()

    def test_cli_main_returns_nonzero_for_upstream_failure(self):
        with (
            patch.object(update_price, "run", side_effect=update_price.UpstreamDataError("timeout")),
            patch.object(update_price.sys, "argv", ["update_price.py", "daily"]),
        ):
            self.assertEqual(update_price.main(), 1)


if __name__ == "__main__":
    unittest.main()
