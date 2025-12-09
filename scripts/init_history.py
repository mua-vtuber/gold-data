"""
초기 히스토리 데이터 생성 스크립트
FreeGoldAPI에서 과거 데이터를 가져와서 history.json에 저장
"""
import json
import requests
from datetime import datetime, timedelta

# FreeGoldAPI에서 역사적 데이터 가져오기
FREE_GOLD_API_URL = "https://freegoldapi.com/data/latest.json"

def fetch_historical_data():
    """FreeGoldAPI에서 역사적 금시세 데이터 가져오기"""
    print("Fetching historical data from FreeGoldAPI...")
    try:
        response = requests.get(FREE_GOLD_API_URL, timeout=60)
        response.raise_for_status()
        data = response.json()
        print(f"Fetched {len(data)} records")
        return data
    except Exception as e:
        print(f"Failed to fetch historical data: {e}")
        return []

def get_average_exchange_rate_for_year(year):
    """연도별 대략적인 환율 (하드코딩)"""
    # 실제로는 환율 API에서 가져와야 하지만, 과거 데이터는 대략적인 값 사용
    exchange_rates = {
        2024: 1350, 2023: 1300, 2022: 1290, 2021: 1150, 2020: 1180,
        2019: 1165, 2018: 1100, 2017: 1130, 2016: 1160, 2015: 1130,
        2014: 1050, 2013: 1095, 2012: 1125, 2011: 1107, 2010: 1155,
        2009: 1275, 2008: 1100, 2007: 930, 2006: 955, 2005: 1025,
        2004: 1145, 2003: 1190, 2002: 1250, 2001: 1290, 2000: 1130,
        1999: 1190, 1998: 1400, 1997: 950, 1996: 805, 1995: 770,
    }
    return exchange_rates.get(year, 1200)  # 기본값 1200

def process_data(raw_data):
    """데이터 처리 및 변환"""
    processed = []

    # 2010년부터 데이터 사용
    cutoff_date = "2010-01-01"

    for item in raw_data:
        date_str = item.get("date", "")
        price = item.get("price", 0)

        # 날짜 필터링
        if date_str < cutoff_date:
            continue

        # 유효한 가격만
        if price <= 0:
            continue

        try:
            year = int(date_str[:4])
            exchange_rate = get_average_exchange_rate_for_year(year)

            # USD/oz -> KRW/g 변환
            international_price_krw = (price / 31.1035) * exchange_rate

            # 한국 금시세 추정 (국제 시세 + 3% 프리미엄 가정)
            korean_price = international_price_krw * 1.03

            # 프리미엄 계산
            premium = 3.0  # 추정값

            processed.append({
                "date": date_str,
                "koreanPrice": round(korean_price, 2),
                "internationalPrice": round(price, 2),
                "internationalPriceKrw": round(international_price_krw, 2),
                "exchangeRate": float(exchange_rate),
                "premium": premium
            })
        except Exception as e:
            print(f"Error processing {date_str}: {e}")
            continue

    # 날짜순 정렬
    processed.sort(key=lambda x: x["date"])

    return processed

def save_history(data):
    """히스토리 파일 저장"""
    history = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
        "data": data
    }

    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(data)} records to history.json")

def main():
    # 1. FreeGoldAPI에서 데이터 가져오기
    raw_data = fetch_historical_data()

    if not raw_data:
        print("No data fetched. Exiting.")
        return

    # 2. 데이터 처리
    processed_data = process_data(raw_data)

    print(f"Processed {len(processed_data)} records (2010-present)")

    if processed_data:
        print(f"Date range: {processed_data[0]['date']} ~ {processed_data[-1]['date']}")

    # 3. 저장
    save_history(processed_data)

    print("Done!")

if __name__ == "__main__":
    main()
