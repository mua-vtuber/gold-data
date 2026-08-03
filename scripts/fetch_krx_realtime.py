import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import requests


OFFICIAL_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=KRW"
TROY_OUNCE_GRAMS = 31.1035


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


def _optional_float(value, label):
    if value in (None, ""):
        return 0.0
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise UpstreamDataError(f"Invalid {label}: {value!r}") from exc
    if not math.isfinite(number):
        raise UpstreamDataError(f"Invalid {label}: {value!r}")
    return number


def _items_from_body(body):
    items = body.get("items", {}).get("item", [])
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return items
    raise UpstreamDataError("Invalid KRX items payload")


def get_krx_gold_price(api_key, now_kst=None):
    """Return the latest official KRX close from a valid recent trading date."""
    if not api_key:
        raise UpstreamDataError("KOREADATA_API_KEY is required")
    kst = timezone(timedelta(hours=9))
    now_kst = now_kst or datetime.now(kst)

    for days_ago in range(10):
        target_date = (now_kst - timedelta(days=days_ago)).strftime("%Y%m%d")
        params = {
            "serviceKey": api_key,
            "pageNo": "1",
            "numOfRows": "10",
            "resultType": "json",
            "basDt": target_date,
        }
        try:
            response = requests.get(OFFICIAL_API_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise UpstreamDataError(
                f"Failed to fetch official KRX price ({type(exc).__name__})"
            ) from exc

        header = payload.get("response", {}).get("header", {})
        if str(header.get("resultCode")) not in {"0", "00"}:
            raise UpstreamDataError(f"KRX API error: {header.get('resultMsg', 'unknown error')}")

        body = payload.get("response", {}).get("body", {})
        for item in _items_from_body(body):
            name = str(item.get("itmsNm", "")).lower()
            if "1kg" in name and "미니" not in name:
                return parse_official_api_item(item)
        print(f"No standard 1kg KRX data for {target_date}; trying the previous date.")

    raise UpstreamDataError("No standard 1kg KRX data found in the last 10 calendar days")


def parse_official_api_item(item):
    raw_date = str(item.get("basDt", ""))
    try:
        datetime.strptime(raw_date, "%Y%m%d")
    except ValueError as exc:
        raise UpstreamDataError(f"Invalid KRX date: {raw_date!r}") from exc

    return {
        "name": item.get("itmsNm", ""),
        "price": _positive_float(item.get("clpr"), "KRX close"),
        "change": _optional_float(item.get("vs"), "KRX change"),
        "changePercent": _optional_float(item.get("fltRt"), "KRX change percent"),
        "high": _optional_float(item.get("hipr"), "KRX high"),
        "low": _optional_float(item.get("lopr"), "KRX low"),
        "volume": int(_optional_float(item.get("trqu"), "KRX volume")),
        "date": raw_date,
    }


def get_international_gold_price(fetched_at):
    try:
        response = requests.get(GOLD_API_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpstreamDataError(
            f"Failed to fetch international gold price ({type(exc).__name__})"
        ) from exc

    price = _positive_float(payload.get("price"), "international gold price")
    as_of = payload.get("updatedAt") or payload.get("timestamp") or fetched_at.isoformat()
    return price, str(as_of)


def get_exchange_rate():
    try:
        response = requests.get(FRANKFURTER_URL, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpstreamDataError(
            f"Failed to fetch exchange rate ({type(exc).__name__})"
        ) from exc

    rate = _positive_float(payload.get("rates", {}).get("KRW"), "USD/KRW rate")
    rate_date = str(payload.get("date", ""))
    try:
        datetime.strptime(rate_date, "%Y-%m-%d")
    except ValueError as exc:
        raise UpstreamDataError(f"Invalid exchange-rate date: {rate_date!r}") from exc
    return rate, rate_date


def build_result(
    fetched_at,
    krx_data,
    international_price,
    international_as_of,
    exchange_rate,
    exchange_rate_date,
):
    international_price_krw = international_price / TROY_OUNCE_GRAMS * exchange_rate
    return {
        "lastUpdated": fetched_at.isoformat(),
        "dataDate": krx_data["date"],
        "korean": {
            "price": round(krx_data["price"], 2),
            "change": round(krx_data["change"], 2),
            "changePercent": round(krx_data["changePercent"], 2),
            "source": "KRX",
        },
        "international": {
            "priceUsd": round(international_price, 2),
            "priceKrw": round(international_price_krw, 2),
            "asOf": international_as_of,
        },
        "exchangeRate": round(exchange_rate, 2),
        "exchangeRateDate": exchange_rate_date,
        "premium": None,
        "premiumAvailable": False,
    }


def run(now_kst=None, api_key=None):
    kst = timezone(timedelta(hours=9))
    now_kst = now_kst or datetime.now(kst)
    api_key = api_key if api_key is not None else os.environ.get("KOREADATA_API_KEY", "")
    if not api_key:
        raise UpstreamDataError("KOREADATA_API_KEY is required")

    print(f"Fetching gold price snapshot at {now_kst.isoformat()}")
    krx_data = get_krx_gold_price(api_key, now_kst)
    international_price, international_as_of = get_international_gold_price(now_kst)
    exchange_rate, exchange_rate_date = get_exchange_rate()
    result = build_result(
        now_kst,
        krx_data,
        international_price,
        international_as_of,
        exchange_rate,
        exchange_rate_date,
    )

    with open("realtime.json", "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, indent=2, ensure_ascii=False)
    print("Saved realtime.json with premium marked unavailable across different as-of times.")
    return 0


def main():
    try:
        return run()
    except UpstreamDataError as exc:
        print(f"Realtime update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
