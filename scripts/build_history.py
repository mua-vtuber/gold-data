# -*- coding: utf-8 -*-
import json
import os
import csv
import requests
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(SCRIPT_DIR)
CSV_DIR = os.path.join(DATA_DIR, "금시세")
OUTPUT_PATH = os.path.join(DATA_DIR, "history.json")

LBMA_API_URL = "https://prices.lbma.org.uk/json/gold_pm.json"
FRANKFURTER_API_URL = "https://api.frankfurter.app"


def load_krx_csv():
    print("Loading KRX CSV files...")
    korean_prices = {}
    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith(".csv")]
    csv_files.sort()

    for filename in csv_files:
        filepath = os.path.join(CSV_DIR, filename)
        try:
            with open(filepath, "r", encoding="euc-kr") as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) < 2:
                        continue
                    date_str = row[0].replace("/", "-")
                    try:
                        price_per_g = float(row[1].replace(",", ""))
                        # CSV 가격은 이미 g당 가격
                        korean_prices[date_str] = price_per_g
                    except ValueError:
                        continue
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue
    print(f"Loaded {len(korean_prices)} Korean price records")
    return korean_prices


def fetch_lbma_data():
    print("Fetching LBMA gold price data...")
    try:
        response = requests.get(LBMA_API_URL, timeout=60)
        response.raise_for_status()
        data = response.json()
        prices = {}
        for item in data:
            date_str = item.get("d", "")
            values = item.get("v", [])
            if date_str >= "2020-01-01" and values and values[0]:
                prices[date_str] = float(values[0])
        print(f"Fetched {len(prices)} LBMA records (2020~)")
        return prices
    except Exception as e:
        print(f"Failed to fetch LBMA data: {e}")
        return {}


def fetch_exchange_rates(start_date, end_date):
    print(f"Fetching exchange rates from {start_date} to {end_date}...")
    rates = {}
    current_start = datetime.strptime(start_date, "%Y-%m-%d")
    final_end = datetime.strptime(end_date, "%Y-%m-%d")

    while current_start < final_end:
        current_end = min(current_start + timedelta(days=365), final_end)
        start_str = current_start.strftime("%Y-%m-%d")
        end_str = current_end.strftime("%Y-%m-%d")
        try:
            url = f"{FRANKFURTER_API_URL}/{start_str}..{end_str}?from=USD&to=KRW"
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            data = response.json()
            for date, rate_data in data.get("rates", {}).items():
                if "KRW" in rate_data:
                    rates[date] = rate_data["KRW"]
            count = len(data.get("rates", {}))
            print(f"  {start_str} ~ {end_str}: {count} records")
        except Exception as e:
            print(f"  Error fetching {start_str} ~ {end_str}: {e}")
        current_start = current_end + timedelta(days=1)
    print(f"Fetched {len(rates)} exchange rate records")
    return rates


def fill_missing_rates(rates, dates):
    sorted_dates = sorted(dates)
    last_rate = None
    for date in sorted_dates:
        if date in rates:
            last_rate = rates[date]
        elif last_rate:
            rates[date] = last_rate
    return rates


def build_history(korean_prices, intl_prices, exchange_rates):
    print("Building history data...")
    all_dates = set(korean_prices.keys())
    exchange_rates = fill_missing_rates(exchange_rates, all_dates)
    history_data = []
    skipped = 0

    for date in sorted(all_dates):
        korean_price = korean_prices.get(date)
        intl_price = intl_prices.get(date)
        exchange_rate = exchange_rates.get(date)

        if not intl_price:
            for i in range(1, 8):
                prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
                if prev in intl_prices:
                    intl_price = intl_prices[prev]
                    break

        if not exchange_rate:
            for i in range(1, 8):
                prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
                if prev in exchange_rates:
                    exchange_rate = exchange_rates[prev]
                    break

        if not korean_price or not intl_price or not exchange_rate:
            skipped += 1
            continue

        intl_price_krw = (intl_price / 31.1035) * exchange_rate
        premium = ((korean_price - intl_price_krw) / intl_price_krw) * 100

        history_data.append({
            "date": date,
            "koreanPrice": round(korean_price, 2),
            "internationalPrice": round(intl_price, 2),
            "internationalPriceKrw": round(intl_price_krw, 2),
            "exchangeRate": round(exchange_rate, 2),
            "premium": round(premium, 2)
        })

    print(f"Built {len(history_data)} records, skipped {skipped}")
    return history_data


def save_history(data):
    history = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "data": data
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"Saved to: {OUTPUT_PATH}")


def main():
    print("=" * 50)
    print("Building Gold Price History Data")
    print("=" * 50)

    korean_prices = load_krx_csv()
    if not korean_prices:
        print("No Korean price data. Exiting.")
        return

    dates = sorted(korean_prices.keys())
    start_date = dates[0]
    end_date = dates[-1]
    print(f"Korean price date range: {start_date} ~ {end_date}")

    intl_prices = fetch_lbma_data()
    exchange_rates = fetch_exchange_rates(start_date, end_date)
    history_data = build_history(korean_prices, intl_prices, exchange_rates)

    if history_data:
        first = history_data[0]
        last = history_data[-1]
        print(f"Final date range: {first['date']} ~ {last['date']}")
        print(f"Total records: {len(history_data)}")

        print("Sample data (first 3):")
        for item in history_data[:3]:
            d, kr, intl, rate, prem = item['date'], item['koreanPrice'], item['internationalPrice'], item['exchangeRate'], item['premium']
            print(f"  {d}: KR={kr}, INTL={intl}, Rate={rate}, Premium={prem}%")

        print("Sample data (last 3):")
        for item in history_data[-3:]:
            d, kr, intl, rate, prem = item['date'], item['koreanPrice'], item['internationalPrice'], item['exchangeRate'], item['premium']
            print(f"  {d}: KR={kr}, INTL={intl}, Rate={rate}, Premium={prem}%")

    save_history(history_data)
    print("Done!")


if __name__ == "__main__":
    main()
