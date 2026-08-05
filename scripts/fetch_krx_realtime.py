import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests


OFFICIAL_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=KRW"
TROY_OUNCE_GRAMS = 31.1035
REQUEST_MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = (10, 30)
KRX_CACHE_MAX_AGE_DAYS = 10
EXCHANGE_RATE_CACHE_MAX_AGE_DAYS = 7


class UpstreamDataError(RuntimeError):
    """Raised when an upstream request fails or returns unusable data."""


class TransientUpstreamDataError(UpstreamDataError):
    """Raised when retries are exhausted for a temporary upstream failure."""


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


def _is_retryable_request_error(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if not isinstance(exc, requests.HTTPError) or exc.response is None:
        return False
    status_code = exc.response.status_code
    return status_code in {408, 429} or 500 <= status_code < 600


def _fetch_json(url, label, *, params=None):
    last_error = None
    for attempt in range(1, REQUEST_MAX_ATTEMPTS + 1):
        try:
            request_options = {"timeout": REQUEST_TIMEOUT}
            if params is not None:
                request_options["params"] = params
            response = requests.get(url, **request_options)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            if not _is_retryable_request_error(exc) or attempt == REQUEST_MAX_ATTEMPTS:
                break
            delay = 2 ** (attempt - 1)
            print(
                f"{label} request attempt {attempt} failed; retrying in {delay}s.",
                file=sys.stderr,
            )
            time.sleep(delay)

    error_class = (
        TransientUpstreamDataError
        if _is_retryable_request_error(last_error)
        else UpstreamDataError
    )
    raise error_class(
        f"Failed to fetch {label} ({type(last_error).__name__})"
    ) from last_error


def _fetch_official_payload(params):
    return _fetch_json(OFFICIAL_API_URL, "official KRX price", params=params)


def get_krx_gold_price(api_key, now_kst=None):
    """Return the latest official KRX close from a valid recent trading date."""
    if not api_key:
        raise UpstreamDataError("KOREADATA_API_KEY is required")
    kst = timezone(timedelta(hours=9))
    now_kst = now_kst or datetime.now(kst)
    params = {
        "serviceKey": api_key,
        "pageNo": "1",
        "numOfRows": "100",
        "resultType": "json",
        "beginBasDt": (now_kst - timedelta(days=9)).strftime("%Y%m%d"),
        "endBasDt": now_kst.strftime("%Y%m%d"),
    }
    payload = _fetch_official_payload(params)

    header = payload.get("response", {}).get("header", {})
    if str(header.get("resultCode")) not in {"0", "00"}:
        raise UpstreamDataError(f"KRX API error: {header.get('resultMsg', 'unknown error')}")

    body = payload.get("response", {}).get("body", {})
    standard_items = []
    for item in _items_from_body(body):
        name = str(item.get("itmsNm", "")).lower()
        if "1kg" in name and "미니" not in name:
            standard_items.append(parse_official_api_item(item))

    if not standard_items:
        raise UpstreamDataError("No standard 1kg KRX data found in the last 10 calendar days")
    return max(standard_items, key=lambda item: item["date"])


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
    payload = _fetch_json(GOLD_API_URL, "international gold price")

    price = _positive_float(payload.get("price"), "international gold price")
    as_of = payload.get("updatedAt") or payload.get("timestamp") or fetched_at.isoformat()
    return price, str(as_of)


def get_exchange_rate():
    payload = _fetch_json(FRANKFURTER_URL, "exchange rate")

    rate = _positive_float(payload.get("rates", {}).get("KRW"), "USD/KRW rate")
    rate_date = str(payload.get("date", ""))
    try:
        datetime.strptime(rate_date, "%Y-%m-%d")
    except ValueError as exc:
        raise UpstreamDataError(f"Invalid exchange-rate date: {rate_date!r}") from exc
    return rate, rate_date


def _load_cached_result():
    try:
        with open("realtime.json", "r", encoding="utf-8") as input_file:
            cached = json.load(input_file)
    except Exception as exc:
        raise UpstreamDataError(
            f"Cached realtime data is unavailable ({type(exc).__name__})"
        ) from exc
    if not isinstance(cached, dict):
        raise UpstreamDataError("Cached realtime data is invalid")
    return cached


def _cache_age_days(raw_date, date_format, now_kst, label):
    try:
        cached_date = datetime.strptime(raw_date, date_format).date()
    except ValueError as exc:
        raise UpstreamDataError(f"Cached {label} date is invalid: {raw_date!r}") from exc
    age_days = (now_kst.date() - cached_date).days
    if age_days < 0:
        raise UpstreamDataError(f"Cached {label} date is in the future: {raw_date!r}")
    return age_days


def _cached_krx_data(now_kst):
    cached = _load_cached_result()
    raw_date = str(cached.get("dataDate", ""))
    age_days = _cache_age_days(raw_date, "%Y%m%d", now_kst, "KRX")
    if age_days > KRX_CACHE_MAX_AGE_DAYS:
        raise UpstreamDataError(f"Cached KRX data is too old: {raw_date!r}")

    korean = cached.get("korean")
    if not isinstance(korean, dict) or korean.get("source") != "KRX":
        raise UpstreamDataError("Cached KRX data is invalid")
    return {
        "price": _positive_float(korean.get("price"), "cached KRX close"),
        "change": _optional_float(korean.get("change"), "cached KRX change"),
        "changePercent": _optional_float(
            korean.get("changePercent"),
            "cached KRX change percent",
        ),
        "date": raw_date,
    }


def _cached_exchange_rate(now_kst):
    cached = _load_cached_result()
    raw_date = str(cached.get("exchangeRateDate", ""))
    age_days = _cache_age_days(raw_date, "%Y-%m-%d", now_kst, "exchange-rate")
    if age_days > EXCHANGE_RATE_CACHE_MAX_AGE_DAYS:
        raise UpstreamDataError(f"Cached exchange-rate data is too old: {raw_date!r}")
    rate = _positive_float(cached.get("exchangeRate"), "cached USD/KRW rate")
    return rate, raw_date


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
    try:
        krx_data = get_krx_gold_price(api_key, now_kst)
    except TransientUpstreamDataError as upstream_error:
        krx_data = _cached_krx_data(now_kst)
        print(
            f"::warning title=KRX API unavailable::{upstream_error}; "
            f"using cached KRX data from {krx_data['date']}.",
            file=sys.stderr,
        )
    international_price, international_as_of = get_international_gold_price(now_kst)
    try:
        exchange_rate, exchange_rate_date = get_exchange_rate()
    except TransientUpstreamDataError as upstream_error:
        exchange_rate, exchange_rate_date = _cached_exchange_rate(now_kst)
        print(
            f"::warning title=Exchange-rate API unavailable::{upstream_error}; "
            f"using cached exchange rate from {exchange_rate_date}.",
            file=sys.stderr,
        )
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
