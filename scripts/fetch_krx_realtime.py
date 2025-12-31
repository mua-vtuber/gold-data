import json
import os
import requests
from datetime import datetime, timedelta, timezone

# 금융위원회 일반상품시세정보 공식 API
OFFICIAL_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
SERVICE_KEY = "81f920f973031035ae7e27058a06035d966ed25b1b4ca0f1c1a3806add8be6d8"

def get_krx_gold_price():
    """금융위원회 공식 API에서 금 시세 가져오기"""
    try:
        # KST 시간대
        kst = timezone(timedelta(hours=9))

        # 최근 5일간 데이터 검색 (휴일/주말/연휴 고려)
        for days_ago in range(5):
            target_date = (datetime.now(kst) - timedelta(days=days_ago)).strftime("%Y%m%d")

            params = {
                "serviceKey": SERVICE_KEY,
                "pageNo": "1",
                "numOfRows": "10",
                "resultType": "json",
                "basDt": target_date
            }

            response = requests.get(OFFICIAL_API_URL, params=params, timeout=10)
            response.raise_for_status()

            result = response.json()

            # API 응답 확인
            header = result.get("response", {}).get("header", {})
            if header.get("resultCode") != "00":
                print(f"API Error: {header.get('resultMsg')}")
                continue

            body = result.get("response", {}).get("body", {})
            total_count = body.get("totalCount", 0)

            if total_count > 0:
                items = body.get("items", {}).get("item", [])

                # 금 99.99_1kg 찾기
                for item in items:
                    itms_nm = item.get("itmsNm", "")
                    if "1kg" in itms_nm.lower() and "미니" not in itms_nm.lower():
                        print(f"Found gold data for {target_date}: {itms_nm}")
                        return parse_official_api_item(item)

                # 1kg 없으면 첫 번째 항목 사용
                if items:
                    print(f"Using first item for {target_date}: {items[0].get('itmsNm')}")
                    return parse_official_api_item(items[0])

            print(f"No data for {target_date}, trying previous day...")

        print("No gold price data found in the last 5 days")
        return None

    except Exception as e:
        print(f"Failed to fetch official API gold price: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_official_api_item(item):
    """공식 API 응답 항목 파싱"""
    def safe_float(val):
        if not val:
            return 0.0
        # 문자열로 변환 후 숫자로
        try:
            return float(str(val))
        except ValueError:
            return 0.0

    def safe_int(val):
        if not val:
            return 0
        try:
            return int(str(val))
        except ValueError:
            return 0

    return {
        "name": item.get("itmsNm", ""),
        "price": safe_float(item.get("clpr", 0)),  # 종가
        "change": safe_float(item.get("vs", 0)),  # 전일대비
        "changePercent": safe_float(item.get("fltRt", 0)),  # 등락률
        "high": safe_float(item.get("hipr", 0)),  # 고가
        "low": safe_float(item.get("lopr", 0)),  # 저가
        "volume": safe_int(item.get("trqu", 0)),  # 거래량
        "date": item.get("basDt", "")
    }

def get_international_gold_price():
    """Gold-API.com에서 국제 금시세 가져오기 (USD/oz)"""
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("price", 0)
    except Exception as e:
        print(f"Failed to fetch international gold price: {e}")
        return None

def get_exchange_rate():
    """Frankfurter API에서 환율 가져오기"""
    try:
        response = requests.get("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("rates", {}).get("KRW", 1400)
    except Exception as e:
        print(f"Failed to fetch exchange rate: {e}")
        return 1400  # 기본값

def main():
    # KST 시간대
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    print(f"Fetching realtime gold price at {now_kst.isoformat()}")

    # 데이터 가져오기
    krx_data = get_krx_gold_price()
    international_price = get_international_gold_price()
    exchange_rate = get_exchange_rate()

    print(f"KRX data: {krx_data}")
    print(f"International price: {international_price} USD/oz")
    print(f"Exchange rate: {exchange_rate} KRW/USD")

    # 한국 금시세
    korean_price = krx_data["price"] if krx_data else 0
    korean_change = krx_data["change"] if krx_data else 0
    korean_change_percent = krx_data["changePercent"] if krx_data else 0
    data_date = krx_data["date"] if krx_data else ""

    # 국제 금시세를 원/g로 변환
    international_price_krw = (international_price / 31.1035) * exchange_rate if international_price else 0

    # 프리미엄 계산
    premium = 0
    if international_price_krw > 0 and korean_price > 0:
        premium = ((korean_price - international_price_krw) / international_price_krw) * 100

    # 결과 저장
    result = {
        "lastUpdated": now_kst.isoformat(),
        "dataDate": data_date,  # 실제 시세 날짜 (YYYYMMDD)
        "korean": {
            "price": round(korean_price, 2),
            "change": round(korean_change, 2),
            "changePercent": round(korean_change_percent, 2),
            "source": "KRX" if krx_data else "estimated"
        },
        "international": {
            "priceUsd": round(international_price, 2) if international_price else 0,
            "priceKrw": round(international_price_krw, 2)
        },
        "exchangeRate": round(exchange_rate, 2),
        "premium": round(premium, 2)
    }

    print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

    # 파일 저장
    with open("realtime.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("Saved to realtime.json")

if __name__ == "__main__":
    main()
