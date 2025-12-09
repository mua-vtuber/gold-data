import json
import os
import requests
from datetime import datetime, timedelta

# API URLs
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
EXCHANGE_RATE_URL = "https://api.frankfurter.app/latest?from=USD&to=KRW"
KRX_API_URL = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"

def get_international_gold_price():
    """Gold-API.com에서 국제 금시세 가져오기 (USD/oz)"""
    try:
        response = requests.get(GOLD_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("price", 0)
    except Exception as e:
        print(f"Failed to fetch international gold price: {e}")
        return None

def get_exchange_rate():
    """Frankfurter API에서 환율 가져오기 (USD/KRW)"""
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("rates", {}).get("KRW", 0)
    except Exception as e:
        print(f"Failed to fetch exchange rate: {e}")
        return None

def get_korean_gold_price(api_key):
    """공공데이터포털에서 한국 금시세 가져오기 (원/g)"""
    try:
        params = {
            "serviceKey": api_key,
            "numOfRows": 5,
            "resultType": "json"
        }
        response = requests.get(KRX_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        # 1kg 금 데이터 찾기
        for item in items:
            if "1Kg" in item.get("itmsNm", "") or "1kg" in item.get("itmsNm", ""):
                price_per_kg = float(item.get("clpr", 0))
                return price_per_kg / 1000  # 원/g로 변환

        # 1kg 없으면 첫 번째 항목 사용
        if items:
            price_per_kg = float(items[0].get("clpr", 0))
            return price_per_kg / 1000

        return None
    except Exception as e:
        print(f"Failed to fetch Korean gold price: {e}")
        return None

def load_history():
    """기존 히스토리 파일 로드"""
    try:
        with open("history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"lastUpdated": "", "data": []}

def save_history(history):
    """히스토리 파일 저장"""
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def main():
    print("Fetching gold price data...")

    # API 키 가져오기
    krx_api_key = os.environ.get("KRX_API_KEY", "")

    # 데이터 가져오기
    international_price = get_international_gold_price()
    exchange_rate = get_exchange_rate()
    korean_price = get_korean_gold_price(krx_api_key) if krx_api_key else None

    print(f"International price: {international_price} USD/oz")
    print(f"Exchange rate: {exchange_rate} KRW/USD")
    print(f"Korean price: {korean_price} KRW/g")

    # 데이터 유효성 확인
    if international_price is None or exchange_rate is None:
        print("Failed to fetch required data. Skipping update.")
        return

    # 한국 금시세가 없으면 추정값 사용
    if korean_price is None or korean_price == 0:
        korean_price = (international_price / 31.1035) * exchange_rate * 1.03
        print(f"Using estimated Korean price: {korean_price} KRW/g")

    # 국제 금시세를 원/g로 변환
    international_price_krw = (international_price / 31.1035) * exchange_rate

    # 프리미엄 계산
    premium = ((korean_price - international_price_krw) / international_price_krw) * 100 if international_price_krw > 0 else 0

    # 오늘 날짜
    today = datetime.now().strftime("%Y-%m-%d")

    # 새 데이터
    new_entry = {
        "date": today,
        "koreanPrice": round(korean_price, 2),
        "internationalPrice": round(international_price, 2),
        "internationalPriceKrw": round(international_price_krw, 2),
        "exchangeRate": round(exchange_rate, 2),
        "premium": round(premium, 2)
    }

    print(f"New entry: {new_entry}")

    # 히스토리 로드
    history = load_history()

    # 오늘 데이터가 이미 있으면 업데이트, 없으면 추가
    existing_index = next((i for i, d in enumerate(history["data"]) if d["date"] == today), None)
    if existing_index is not None:
        history["data"][existing_index] = new_entry
        print(f"Updated existing entry for {today}")
    else:
        history["data"].append(new_entry)
        print(f"Added new entry for {today}")

    # 날짜순 정렬
    history["data"].sort(key=lambda x: x["date"])

    # 90일 이상 된 데이터 삭제
    cutoff_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    history["data"] = [d for d in history["data"] if d["date"] >= cutoff_date]

    # 업데이트 시간 기록
    history["lastUpdated"] = today

    # 저장
    save_history(history)
    print(f"History saved. Total entries: {len(history['data'])}")

if __name__ == "__main__":
    main()
