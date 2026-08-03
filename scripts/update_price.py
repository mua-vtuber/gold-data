import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import requests


KRX_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
LBMA_API_URL = "https://prices.lbma.org.uk/json/gold_pm.json"
FRANKFURTER_API_URL = "https://api.frankfurter.app"
TROY_OUNCE_GRAMS = 31.1035
PAGE_SIZE = 1000


class UpstreamDataError(RuntimeError):
    """Raised when an upstream request fails or returns unusable data."""


def _positive_float(value, label):
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise UpstreamDataError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise UpstreamDataError(f"Invalid {label}: {value!r}")
    return number


def _items_from_body(body):
    items = body.get("items", {}).get("item", [])
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return items
    raise UpstreamDataError("Invalid KRX items payload")


def _is_standard_1kg(item):
    name = str(item.get("itmsNm") or item.get("ISU_ABBRV") or "").lower()
    return "1kg" in name and "미니" not in name


def get_korean_gold_prices(api_key, start_date, end_date):
    """Return every official KRX 1kg close in the inclusive date range."""
    if not api_key:
        raise UpstreamDataError("KOREADATA_API_KEY is required")

    prices = {}
    page = 1
    reported_total = 0
    while True:
        params = {
            "serviceKey": api_key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "resultType": "json",
            "beginBasDt": start_date.replace("-", ""),
            "endBasDt": end_date.replace("-", ""),
        }
        try:
            response = requests.get(KRX_API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise UpstreamDataError(
                f"Failed to fetch KRX history ({type(exc).__name__})"
            ) from exc

        header = payload.get("response", {}).get("header", {})
        if str(header.get("resultCode")) not in {"0", "00"}:
            raise UpstreamDataError(f"KRX API error: {header.get('resultMsg', 'unknown error')}")

        body = payload.get("response", {}).get("body", {})
        items = _items_from_body(body)
        for item in items:
            if not _is_standard_1kg(item):
                continue
            raw_date = str(item.get("basDt", ""))
            try:
                date = datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError as exc:
                raise UpstreamDataError(f"Invalid KRX date: {raw_date!r}") from exc
            prices[date] = _positive_float(item.get("clpr"), f"KRX close for {date}")

        try:
            total_count = int(body.get("totalCount", len(items)))
            returned_page_size = int(body.get("numOfRows", PAGE_SIZE))
        except (TypeError, ValueError) as exc:
            raise UpstreamDataError("Invalid KRX pagination metadata") from exc
        if returned_page_size <= 0:
            raise UpstreamDataError("Invalid KRX numOfRows")
        reported_total = max(reported_total, total_count)
        if page * returned_page_size >= total_count:
            break
        page += 1

    if reported_total > 0 and not prices:
        raise UpstreamDataError("KRX returned records but no standard 1kg gold prices")
    return prices


def fetch_lbma_prices():
    """Return LBMA PM USD/oz prices keyed by their actual publication date."""
    try:
        response = requests.get(LBMA_API_URL, timeout=60)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpstreamDataError(
            f"Failed to fetch LBMA prices ({type(exc).__name__})"
        ) from exc

    prices = {}
    for item in payload:
        date = str(item.get("d", ""))
        values = item.get("v", [])
        if values and values[0] is not None:
            prices[date] = _positive_float(values[0], f"LBMA price for {date}")
    if not prices:
        raise UpstreamDataError("LBMA returned no usable prices")
    return prices


def fetch_exchange_rates(start_date, end_date):
    """Return Frankfurter USD/KRW rates keyed by their actual rate date."""
    url = f"{FRANKFURTER_API_URL}/{start_date}..{end_date}?from=USD&to=KRW"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpstreamDataError(
            f"Failed to fetch exchange rates ({type(exc).__name__})"
        ) from exc

    raw_rates = payload.get("rates")
    if not isinstance(raw_rates, dict):
        raise UpstreamDataError("Frankfurter returned an invalid rates payload")

    rates = {}
    for date, rate_data in raw_rates.items():
        if "KRW" in rate_data:
            rates[date] = _positive_float(rate_data["KRW"], f"USD/KRW rate for {date}")
    return rates


def build_entries(korean_prices, international_prices, exchange_rates):
    """Build history rows only from values sharing the exact same market date."""
    entries = []
    for date in sorted(korean_prices):
        korean_price = _positive_float(korean_prices[date], f"KRX close for {date}")
        if date not in international_prices or date not in exchange_rates:
            entries.append(
                {
                    "date": date,
                    "koreanPrice": round(korean_price, 2),
                    "internationalPrice": None,
                    "internationalPriceKrw": None,
                    "exchangeRate": None,
                    "premium": None,
                    "premiumAvailable": False,
                }
            )
            continue

        international_price = _positive_float(
            international_prices[date], f"LBMA price for {date}"
        )
        exchange_rate = _positive_float(exchange_rates[date], f"USD/KRW rate for {date}")
        international_price_krw = international_price / TROY_OUNCE_GRAMS * exchange_rate
        premium = (korean_price - international_price_krw) / international_price_krw * 100
        entries.append(
            {
                "date": date,
                "koreanPrice": round(korean_price, 2),
                "internationalPrice": round(international_price, 2),
                "internationalPriceKrw": round(international_price_krw, 2),
                "exchangeRate": round(exchange_rate, 2),
                "premium": round(premium, 2),
                "premiumAvailable": True,
            }
        )
    return entries


def load_history():
    try:
        with open("history.json", "r", encoding="utf-8") as history_file:
            return json.load(history_file)
    except FileNotFoundError:
        return {"lastUpdated": "", "data": []}


def save_history(history):
    with open("history.json", "w", encoding="utf-8") as history_file:
        json.dump(history, history_file, indent=2, ensure_ascii=False)


def validate_history(history, official_dates=None):
    """Reject malformed, incomplete, or internally inconsistent history."""
    data = history.get("data")
    if not isinstance(data, list):
        raise UpstreamDataError("History data must be a list")

    dates = [str(item.get("date", "")) for item in data]
    if len(dates) != len(set(dates)):
        raise UpstreamDataError("Duplicate dates found in history")
    if dates != sorted(dates):
        raise UpstreamDataError("History dates are not sorted")
    if data and history.get("lastUpdated") != dates[-1]:
        raise UpstreamDataError("History lastUpdated does not match its latest date")

    missing_official_dates = sorted(set(official_dates or ()) - set(dates))
    if missing_official_dates:
        raise UpstreamDataError(
            "History is missing official KRX dates: " + ", ".join(missing_official_dates)
        )

    comparison_fields = (
        "internationalPrice",
        "internationalPriceKrw",
        "exchangeRate",
        "premium",
    )
    for item in data:
        date = str(item.get("date", ""))
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise UpstreamDataError(f"Invalid history date: {date!r}") from exc
        korean_price = _positive_float(item.get("koreanPrice"), f"history KRX price for {date}")

        if item.get("premiumAvailable", True) is False:
            if any(item.get(field) is not None for field in comparison_fields):
                raise UpstreamDataError(
                    f"Unavailable premium fields must be null for {date}"
                )
            continue

        international_price = _positive_float(
            item.get("internationalPrice"), f"history LBMA price for {date}"
        )
        international_price_krw = _positive_float(
            item.get("internationalPriceKrw"), f"history converted price for {date}"
        )
        exchange_rate = _positive_float(
            item.get("exchangeRate"), f"history exchange rate for {date}"
        )
        try:
            premium = float(item.get("premium"))
        except (TypeError, ValueError) as exc:
            raise UpstreamDataError(f"Invalid history premium for {date}") from exc
        if not math.isfinite(premium):
            raise UpstreamDataError(f"Invalid history premium for {date}")

        calculated_krw = international_price / TROY_OUNCE_GRAMS * exchange_rate
        expected_krw = round(calculated_krw, 2)
        if abs(international_price_krw - expected_krw) > 0.011:
            raise UpstreamDataError(f"Inconsistent converted price for {date}")
        expected_premium = round(
            (korean_price - calculated_krw) / calculated_krw * 100,
            2,
        )
        if abs(premium - expected_premium) > 0.011:
            raise UpstreamDataError(f"Inconsistent premium for {date}")


def run(mode, now_kst=None, koreadata_api_key=None):
    if mode not in {"daily", "realtime"}:
        raise ValueError(f"Unsupported mode: {mode}")

    kst = timezone(timedelta(hours=9))
    now_kst = now_kst or datetime.now(kst)
    today = now_kst.strftime("%Y-%m-%d")
    api_key = koreadata_api_key if koreadata_api_key is not None else os.environ.get(
        "KOREADATA_API_KEY", ""
    )

    history = load_history()
    existing_dates = {str(item["date"]) for item in history.get("data", [])}
    start_date = min(existing_dates) if existing_dates else (now_kst - timedelta(days=30)).strftime(
        "%Y-%m-%d"
    )
    print(f"Mode: {mode}; scanning official KRX dates from {start_date} through {today}")

    # The official API publishes KRX data on the following business day. Do not
    # mix a same-day KRX close with LBMA/FX values that have not closed yet.
    korean_prices = get_korean_gold_prices(api_key, start_date, today)

    missing_prices = {
        date: price for date, price in korean_prices.items() if date not in existing_dates
    }
    if not missing_prices:
        validate_history(history, korean_prices)
        print("KRX request succeeded; no missing trading dates were found.")
        return 0

    missing_dates = sorted(missing_prices)
    print(f"Found {len(missing_dates)} missing KRX trading dates: {', '.join(missing_dates)}")
    international_prices = fetch_lbma_prices()
    exchange_rates = fetch_exchange_rates(missing_dates[0], missing_dates[-1])
    new_entries = build_entries(missing_prices, international_prices, exchange_rates)

    updated_data = list(history.get("data", [])) + new_entries
    updated_data.sort(key=lambda item: item["date"])
    updated_history = {
        **history,
        "lastUpdated": updated_data[-1]["date"],
        "data": updated_data,
    }
    validate_history(updated_history, korean_prices)
    save_history(updated_history)
    print(f"Saved {len(new_entries)} entries. Total entries: {len(updated_data)}")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    try:
        return run(mode)
    except (UpstreamDataError, ValueError) as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
