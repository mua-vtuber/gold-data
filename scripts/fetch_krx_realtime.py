import json
import os
import requests
from datetime import datetime

# 공공데이터포털 KRX 금시세 API
KRX_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"

def get_krx_gold_price():
    """공공데이터포털에서 KRX 금 시세 가져오기"""
    try:
        api_key = os.environ.get("KRX_API_KEY", "")
        if not api_key:
            print("KRX_API_KEY not set")
            return None

        params = {
            "serviceKey": api_key,
            "numOfRows": 5,
            "pageNo": 1,
            "resultType": "json"
        }

        response = requests.get(KRX_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        # 금 99.99_1Kg 찾기
        for item in items:
            itms_nm = item.get("itmsNm", "").lower()
            if "1kg" in itms_nm and "미니" not in itms_nm:
                return {
                    "name": item.get("itmsNm", ""),
                    "price": float(item.get("clpr", 0)),  # 이미 원/g 단위
                    "change": float(item.get("vs", 0)),
                    "changePercent": float(item.get("fltRt", 0)),
                    "high": float(item.get("hipr", 0)),
                    "low": float(item.get("lopr", 0)),
                    "volume": item.get("trqu", "0"),
                    "date": item.get("basDt", "")
                }

        # 1Kg 없으면 첫 번째 항목 사용
        if items:
            item = items[0]
            return {
                "name": item.get("itmsNm", ""),
                "price": float(item.get("clpr", 0)),
                "change": float(item.get("vs", 0)),
                "changePercent": float(item.get("fltRt", 0)),
                "high": float(item.get("hipr", 0)),
                "low": float(item.get("lopr", 0)),
                "volume": item.get("trqu", "0"),
                "date": item.get("basDt", "")
            }

        return None
    except Exception as e:
        print(f"Failed to fetch KRX gold price: {e}")
        import traceback
        traceback.print_exc()
        return None

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
    print(f"Fetching realtime gold price at {datetime.now().isoformat()}")

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

    # 국제 금시세를 원/g로 변환
    international_price_krw = (international_price / 31.1035) * exchange_rate if international_price else 0

    # 프리미엄 계산
    premium = 0
    if international_price_krw > 0 and korean_price > 0:
        premium = ((korean_price - international_price_krw) / international_price_krw) * 100

    # 결과 저장
    result = {
        "lastUpdated": datetime.now().isoformat(),
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
